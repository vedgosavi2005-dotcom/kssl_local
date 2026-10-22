import { useCallback, useEffect, useLayoutEffect, useReducer, useRef, useState } from "react";
import Canvas from "./Canvas.jsx";
import Dock from "./Dock.jsx";
import Launcher from "./Launcher.jsx";
import { chat, getConversation, getSavedView, getStatus, saveTranscript, saveView } from "./api.js";
import { focusBlock, getPageContext, navigate, pageLabel, pageSuggestions, productFrame, routeProductAsks, routeProductAssistant } from "./bridge.js";
import { guardProduct } from "./layoutGuard.js";
import { DOM, setRuntime } from "./product.js";

const STORE_KEY = "pa-session-v1";
const MAX_SAVED_VIEWS = 8;

const initial = {
  convId: null,
  messages: [],
  views: {},          // id -> hydrated view spec
  order: [],          // view ids, oldest first
  active: null,       // view id shown on the canvas
  canvas: false,
  busy: false,
  pending: null,      // a view on its way: {title, stage, after} -- the canvas shows its frame
  saved: [],          // view ids saved to History
};

function load() {
  try {
    const s = JSON.parse(sessionStorage.getItem(STORE_KEY) || "null");
    if (s && Array.isArray(s.messages)) return { ...initial, ...s, busy: false, canvas: false, pending: null };
  } catch (e) {
    /* storage unavailable or corrupt: start fresh */
  }
  return initial;
}

// the session's chat, kept in sessionStorage (not the same as the component's save(view) for a canvas view)
function persistSession(state) {
  try {
    const order = state.order.slice(-MAX_SAVED_VIEWS);
    const views = Object.fromEntries(order.map((id) => [id, state.views[id]]).filter(([, v]) => v));
    sessionStorage.setItem(STORE_KEY, JSON.stringify({
      convId: state.convId, messages: state.messages.filter((m) => m.role === "user" || m.done), views, order, active: state.active, saved: state.saved,
    }));
  } catch (e) {
    /* quota or privacy mode: the session simply won't survive a reload */
  }
}

const patchLast = (messages, fn) => {
  const i = messages.length - 1;
  if (i < 0 || messages[i].role !== "assistant") return messages;
  const next = messages.slice();
  next[i] = fn(next[i]);
  return next;
};

function reducer(state, a) {
  switch (a.type) {
    case "send":
      return {
        ...state,
        busy: true,
        messages: [
          ...state.messages,
          { id: `u${Date.now()}`, role: "user", text: a.text },
          { id: `a${Date.now()}`, role: "assistant", text: "", status: "Starting", steps: [], notice: null, error: "", done: false, t0: Date.now(), sawView: false },
        ],
      };
    case "event": {
      const ev = a.ev;
      if (ev.type === "meta") {
        // the service no longer knows this chat (it restarted, or the chat expired): say so
        // rather than let a follow-up silently lose its context
        const lost = !!state.convId && ev.conversation_id !== state.convId && state.messages.length > 2;
        return { ...state, convId: ev.conversation_id,
          messages: lost ? patchLast(state.messages, (m) => ({ ...m, contextLost: true })) : state.messages };
      }
      if (ev.type === "view_pending") {
        return { ...state, canvas: true, pending: { title: ev.title, stage: "Designing the view", after: state.active } };
      }
      if (ev.type === "view") {
        const v = ev.spec;
        const known = state.order.includes(v.id);
        return {
          ...state,
          pending: null,
          views: { ...state.views, [v.id]: v },
          order: known ? state.order : [...state.order, v.id],
          active: v.id,
          canvas: true,
          messages: patchLast(state.messages, (m) => ({ ...m, sawView: true,
            steps: [...m.steps, { kind: "view", id: v.id, title: v.title, reopened: !!ev.reopened }] })),
        };
      }
      return {
        ...state,
        // a navigation with no view in the same answer shows the page it opened
        canvas: ev.type === "navigate" && !(state.messages[state.messages.length - 1] || {}).sawView ? false : state.canvas,
        pending: state.pending && ev.type === "status" && (ev.stage === "design" || ev.stage === "review")
          ? { ...state.pending, stage: ev.stage === "review" ? "Checking the design" : "Designing the view" }
          : state.pending,
        messages: patchLast(state.messages, (m) => {
          switch (ev.type) {
            case "status":
              return { ...m, status: ev.text };
            case "text":
              return { ...m, text: m.text + ev.text };
            case "text_break":
              return m.text && !m.text.endsWith("\n\n") ? { ...m, text: `${m.text}\n\n` } : m;
            case "query":
              return { ...m, steps: [...m.steps, { kind: "query", ...ev }] };
            case "navigate":
              return { ...m, steps: [...m.steps, { kind: "navigate", label: ev.label, pillar: ev.pillar, view: ev.view, payload: ev.payload, focus: ev.focus }] };
            case "verify":
              return { ...m, verify: { status: ev.status, checked: ev.checked, issues: ev.issues || [] } };
            case "notice":
              return { ...m, notice: { kind: ev.kind, text: ev.text, suggestions: ev.suggestions || [] } };
            case "error":
              return { ...m, error: ev.text, retry: !!ev.retry };
            case "done":
              return { ...m, done: true, status: "", t1: Date.now() };
            default:
              return m;
          }
        }),
      };
    }
    case "failed":
      return { ...state, busy: false, pending: null, messages: patchLast(state.messages, (m) => ({ ...m, done: true, status: "", error: m.error || a.text, retry: a.retry, t1: Date.now() })) };
    case "finished":
      return { ...state, busy: false, pending: null, messages: patchLast(state.messages, (m) => (m.done ? m : { ...m, done: true, status: "", t1: Date.now() })) };
    case "show":
      return { ...state, active: a.id, canvas: true };
    case "canvas":
      return { ...state, canvas: a.open && !!state.active };
    case "clear":
      return { ...initial };
    case "load": {
      // a conversation reopened from History: its transcript, its views, and the server
      // side restores its memory on the next question
      const views = Object.fromEntries((a.views || []).map((v) => [v.id, v]));
      return { ...initial, convId: a.id, messages: a.messages || [], views, order: (a.views || []).map((v) => v.id),
        active: (a.views || []).length ? a.views[a.views.length - 1].id : null };
    }
    case "addView": {
      const v = a.view;
      return { ...state, views: { ...state.views, [v.id]: v }, order: state.order.includes(v.id) ? state.order : [...state.order, v.id],
        active: v.id, canvas: true, saved: a.saved && !state.saved.includes(v.id) ? [...state.saved, v.id] : state.saved };
    }
    case "saved":
      return state.saved.includes(a.id) ? state : { ...state, saved: [...state.saved, a.id] };
    default:
      return state;
  }
}

export default function App() {
  const [state, dispatch] = useReducer(reducer, undefined, load);
  const [status, setStatus] = useState(null);
  const [budget, setBudget] = useState(null);
  // The dock is CLOSED until the product's own "Ask Parallax" button opens it, so with the
  // chat closed the product looks exactly as shipped. Remembered for the browser session.
  const [open, setOpenState] = useState(() => {
    try {
      return sessionStorage.getItem("pa-open") === "1";
    } catch (e) {
      return false;
    }
  });
  const setOpen = useCallback((v) => {
    setOpenState(v);
    try {
      sessionStorage.setItem("pa-open", v ? "1" : "0");
    } catch (e) {
      /* not remembered */
    }
  }, []);
  // our own button when the product has no "Ask Parallax" of its own (or it went missing)
  const [launcher, setLauncher] = useState(!DOM.assistant_button);
  const [frame, setFrame] = useState({ top: 46, left: 206 });
  const [pageText, setPageText] = useState("");
  const [suggestions, setSuggestions] = useState([]);
  const abortRef = useRef(null);
  const stateRef = useRef(state);
  stateRef.current = state;

  useEffect(() => {
    getStatus()
      .then((s) => {
        setRuntime(s); // the client's name and the company colours, when they come from the data
        setStatus(s);
        setBudget(s.budget);
      })
      .catch(() => setStatus({ enabled: false, error: "The agent service is not reachable." }));
  }, []);

  useEffect(() => {
    if (!state.busy) persistSession(state);
  }, [state]);

  // the product's layout hook: room for the dock, only while it is open
  useEffect(() => {
    const html = document.documentElement;
    html.classList.toggle("pa-on", open);
    if (!open) html.classList.remove("pa-overlay");
    return undefined;
  }, [open]);
  // where the canvas sits: measured from the product's own layout, synchronously before
  // paint (so it never flashes in the wrong place) and again on resize
  useLayoutEffect(() => {
    document.documentElement.classList.toggle("pa-view-open", state.canvas);
    const measure = () => {
      const f = productFrame();
      setFrame((prev) => (prev.top === f.top && prev.left === f.left ? prev : f));
    };
    measure();
    const t = setTimeout(measure, 250); // after the dock's width transition settles
    window.addEventListener("resize", measure);
    return () => {
      clearTimeout(t);
      window.removeEventListener("resize", measure);
    };
  }, [state.canvas, open]);

  // where the user is, for the dock's context line (the product has no route event to listen to)
  useEffect(() => {
    const tick = () => {
      const ctx = getPageContext();
      setPageText(pageLabel(ctx));
      const next = pageSuggestions(ctx);
      setSuggestions((prev) => (prev.join("|") === next.join("|") ? prev : next));
    };
    tick();
    const t = setInterval(tick, 1200);
    return () => clearInterval(t);
  }, []);

  // the product's own "Ask Parallax" button opens this dock; if the product ever drops that
  // button, a launcher of our own appears in its place
  useEffect(() => {
    const off = routeProductAssistant(() => {
      setOpen(true);
      setTimeout(() => window.dispatchEvent(new Event("pa-focus-input")), 30);
    });
    const t = DOM.assistant_button ? setTimeout(() => setLauncher(!document.querySelector(DOM.assistant_button)), 5000) : null;
    return () => {
      off();
      if (t) clearTimeout(t);
    };
  }, [setOpen]);

  // layout guardian: keep the product undistorted at this window size (falls back to overlay)
  useEffect(() => {
    const run = () => guardProduct();
    const t = setTimeout(run, 1500);
    window.addEventListener("resize", run);
    return () => {
      clearTimeout(t);
      window.removeEventListener("resize", run);
    };
  }, [open]);

  // Esc closes the canvas; using the product's own navigation (rail, pillar tabs) does too
  useEffect(() => {
    const onKey = (e) => {
      if (e.key === "Escape" && stateRef.current.canvas) dispatch({ type: "canvas", open: false });
    };
    const onClick = (e) => {
      if (!stateRef.current.canvas) return;
      if (e.target.closest && e.target.closest(`${DOM.rail}, ${DOM.topbar}`)) dispatch({ type: "canvas", open: false });
    };
    window.addEventListener("keydown", onKey);
    document.addEventListener("click", onClick, true);
    return () => {
      window.removeEventListener("keydown", onKey);
      document.removeEventListener("click", onClick, true);
    };
  }, []);

  const send = useCallback(async (text) => {
    const q = String(text || "").trim();
    if (!q || stateRef.current.busy) return;
    setOpen(true);
    dispatch({ type: "send", text: q });
    const page = getPageContext();
    const st = stateRef.current;
    if (st.canvas && st.active && st.views[st.active]) page.canvas = st.views[st.active].title;
    const ctrl = new AbortController();
    abortRef.current = ctrl;
    try {
      await chat({
        conversationId: st.convId,
        message: q,
        page,
        signal: ctrl.signal,
        onEvent: (ev) => {
          if (ev.type === "navigate") {
            navigate(ev.pillar, ev.view, ev.payload);
            if (ev.focus) focusBlock(ev.focus);
          }
          if (ev.type === "done" && ev.budget) setBudget(ev.budget);
          dispatch({ type: "event", ev });
        },
      });
      dispatch({ type: "finished" });
    } catch (e) {
      dispatch(e.name === "AbortError"
        ? { type: "failed", text: "Stopped." }
        : { type: "failed", text: "The assistant could not be reached. Check your connection and try again.", retry: true });
    } finally {
      abortRef.current = null;
    }
  }, []);

  const sendRef = useRef(send);
  sendRef.current = send;

  const stop = () => abortRef.current && abortRef.current.abort();

  // the product's own panel "Ask" boxes go to the agent while this widget runs
  useEffect(() => routeProductAsks((q) => {
    setOpen(true);
    sendRef.current(q);
  }), [setOpen]);

  // a share link (?pa-view=<id>) opens that saved view
  useEffect(() => {
    let id = null;
    try {
      id = new URLSearchParams(window.location.search).get("pa-view");
    } catch (e) {
      /* no query string */
    }
    if (!id) return;
    getSavedView(id)
      .then((view) => {
        setOpen(true);
        dispatch({ type: "addView", view, saved: true });
      })
      .catch(() => {});
  }, [setOpen]);

  // after each answer, the transcript goes to History (the server keeps the agent's memory)
  useEffect(() => {
    const st = stateRef.current;
    if (st.busy || !st.convId || !st.messages.length) return;
    const first = st.messages.find((m) => m.role === "user");
    saveTranscript(st.convId, first ? first.text : "Conversation", st.messages.filter((m) => m.role === "user" || m.done));
  }, [state.busy, state.convId]);

  // ↺: a fresh conversation; the old one stays in History
  const reset = () => {
    stop();
    dispatch({ type: "clear" });
    setTimeout(() => window.dispatchEvent(new Event("pa-focus-input")), 30);
  };

  const openConversation = async (id) => {
    stop();
    const c = await getConversation(id);
    dispatch({ type: "load", id: c.id, messages: c.transcript, views: c.views });
  };

  const openSavedView = async (id) => {
    const view = await getSavedView(id);
    dispatch({ type: "addView", view, saved: true });
  };

  const save = async (view) => {
    await saveView(view, stateRef.current.convId);
    dispatch({ type: "saved", id: view.id });
  };

  const share = async (view) => {
    if (!stateRef.current.saved.includes(view.id)) await save(view);
    const url = `${window.location.origin}${window.location.pathname}?pa-view=${encodeURIComponent(view.id)}${window.location.hash}`;
    await navigator.clipboard.writeText(url);
  };

  const closeDock = () => {
    dispatch({ type: "canvas", open: false });
    setOpen(false);
  };

  const openPage = (pillar, view, payload, focus) => {
    navigate(pillar, view, payload);
    dispatch({ type: "canvas", open: false });
    if (focus) focusBlock(focus);
  };

  const idx = state.order.indexOf(state.active);
  const activeView = state.active ? state.views[state.active] : null;

  const debug = !!(status && status.debug_ui);

  if (!open) {
    return launcher ? <Launcher onOpen={() => { setOpen(true); setTimeout(() => window.dispatchEvent(new Event("pa-focus-input")), 30); }} /> : null;
  }

  return (
    <>
      {state.canvas && (activeView || state.pending) ? (
        <Canvas
          debug={debug}
          onSave={save}
          onShare={share}
          pending={state.pending}
          saved={!!activeView && state.saved.includes(activeView.id)}
          frame={frame}
          index={idx}
          onAsk={send}
          onClose={() => dispatch({ type: "canvas", open: false })}
          onNavigate={(p, v, payload) => openPage(p, v, payload)}
          onNext={() => dispatch({ type: "show", id: state.order[idx + 1] })}
          onPrev={() => dispatch({ type: "show", id: state.order[idx - 1] })}
          total={state.order.length}
          view={activeView}
        />
      ) : null}
      <Dock
        budget={budget}
        busy={state.busy}
        canvasOpen={state.canvas}
        debug={debug}
        hasViews={state.order.length > 0}
        messages={state.messages}
        onClose={closeDock}
        onReset={reset}
        onOpenConversation={openConversation}
        onOpenSavedView={openSavedView}
        suggestions={suggestions}
        onOpenPage={openPage}
        onSend={send}
        onShowView={(id) => dispatch({ type: "show", id })}
        onStop={stop}
        onToggleCanvas={() => dispatch({ type: "canvas", open: !state.canvas })}
        pageText={pageText}
        status={status}
        views={state.views}
      />
    </>
  );
}
