from telegram import InlineKeyboardButton, InlineKeyboardMarkup


CALLBACK_PREFIX = "interactive:"
CALLBACK_UP = f"{CALLBACK_PREFIX}scroll:up"
CALLBACK_DOWN = f"{CALLBACK_PREFIX}scroll:down"
CALLBACK_KEY_1 = f"{CALLBACK_PREFIX}key:1"
CALLBACK_KEY_2 = f"{CALLBACK_PREFIX}key:2"
CALLBACK_ENTER = f"{CALLBACK_PREFIX}key:enter"
CALLBACK_ESC = f"{CALLBACK_PREFIX}key:esc"
CALLBACK_CTRL_C = f"{CALLBACK_PREFIX}ctrlc"
CALLBACK_EXIT = f"{CALLBACK_PREFIX}exit"

KEY_INPUTS = {
    CALLBACK_KEY_1: "1",
    CALLBACK_KEY_2: "2",
    CALLBACK_ENTER: "\r",
    CALLBACK_ESC: "\x1b",
}


def callback_input(callback_data: str) -> str | None:
    return KEY_INPUTS.get(callback_data)


def interactive_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("Up", callback_data=CALLBACK_UP),
            InlineKeyboardButton("Down", callback_data=CALLBACK_DOWN),
        ],
        [
            InlineKeyboardButton("1", callback_data=CALLBACK_KEY_1),
            InlineKeyboardButton("2", callback_data=CALLBACK_KEY_2),
            InlineKeyboardButton("Enter", callback_data=CALLBACK_ENTER),
            InlineKeyboardButton("Esc", callback_data=CALLBACK_ESC),
        ],
        [
            InlineKeyboardButton("Ctrl-C", callback_data=CALLBACK_CTRL_C),
            InlineKeyboardButton("Close", callback_data=CALLBACK_EXIT),
        ],
    ])
