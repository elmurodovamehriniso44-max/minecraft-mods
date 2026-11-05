"""Handlerlar paketi. Tartib muhim: music.py'dagi umumiy matn handler'i eng oxirida bo'lishi kerak."""
from . import admin, inline, music, start

routers = [start.router, admin.router, inline.router, music.router]
