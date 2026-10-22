"""Parallax Analyst: the agentic chat behind "Ask Parallax".

Three agents, one endpoint (POST /api/agent/chat, server-sent events):

  guard         -- small model, decides in-scope / off-topic before anything runs
  orchestrator  -- plans the answer, talks to the user, calls the tools below
    query_data    -> data agent: writes read-only SQL over analytics.*, can LLM-categorise rows
    show_insight  -> UI agent: composes a view spec from the widget catalog
    navigate      -> tells the frontend to open a page (AppState.jumpTo)

Numbers only ever come from SQL results held server-side by id; the UI agent references
result ids and columns, and the server attaches the rows to the spec it sends. No model
retypes a figure into a chart.

app.py mounts agent.routes.router.
"""
