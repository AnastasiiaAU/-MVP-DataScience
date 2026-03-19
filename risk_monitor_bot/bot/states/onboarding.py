from aiogram.fsm.state import State, StatesGroup


class OnboardingStates(StatesGroup):
    choosing_industry = State()
    choosing_region = State()
    choosing_threshold = State()
