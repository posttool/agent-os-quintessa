from quintessa.api.routes import agent, ambient, apps, cards, persona, questions, settings, tools

ROUTERS = [r.router for r in (agent, questions, cards, tools, apps, ambient, persona, settings)]
