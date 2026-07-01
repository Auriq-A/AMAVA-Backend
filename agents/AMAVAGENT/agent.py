"""ADK app entrypoint, named to match the frontend's appName ('AMAVAGENT').

`adk api_server` names each app after its folder. The frontend posts to
/apps/AMAVAGENT/... and /run with appName='AMAVAGENT', so the folder must be
'AMAVAGENT'. The real multi-tenant agent lives in the `amava_agent` package;
this just re-exports it so we don't have to rename the package (which other
code imports as `amava_agent`).
"""
from amava_agent.agent import root_agent  # noqa: F401  (ADK discovers root_agent)
