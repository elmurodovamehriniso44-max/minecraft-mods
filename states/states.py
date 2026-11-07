"""FSM holatlari."""
from aiogram.fsm.state import State, StatesGroup


class SearchState(StatesGroup):
    query = State()


class RequestState(StatesGroup):
    text = State()


class AddMod(StatesGroup):
    name = State()
    description = State()
    category = State()
    author = State()
    versions = State()
    preview = State()
    file = State()
    instructions = State()


class EditMod(StatesGroup):
    value = State()
    preview = State()
    file = State()
