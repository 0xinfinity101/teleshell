import unittest

from interactive_controls import (
    CALLBACK_CTRL_C,
    CALLBACK_DOWN,
    CALLBACK_ENTER,
    CALLBACK_EXIT,
    CALLBACK_KEY_1,
    CALLBACK_KEY_2,
    CALLBACK_UP,
    callback_input,
    interactive_keyboard,
)


class InteractiveControlsTest(unittest.TestCase):
    def test_keyboard_contains_choice_enter_control_and_close_buttons(self):
        keyboard = interactive_keyboard().inline_keyboard

        labels = [[button.text for button in row] for row in keyboard]
        callbacks = [[button.callback_data for button in row] for row in keyboard]

        self.assertEqual(labels, [["Up", "Down"], ["1", "2", "Enter", "Esc"], ["Ctrl-C", "Close"]])
        self.assertEqual(
            callbacks,
            [
                [CALLBACK_UP, CALLBACK_DOWN],
                [CALLBACK_KEY_1, CALLBACK_KEY_2, CALLBACK_ENTER, "interactive:key:esc"],
                [CALLBACK_CTRL_C, CALLBACK_EXIT],
            ],
        )

    def test_callback_input_maps_buttons_to_raw_terminal_input(self):
        self.assertEqual(callback_input(CALLBACK_KEY_1), "1")
        self.assertEqual(callback_input(CALLBACK_KEY_2), "2")
        self.assertEqual(callback_input(CALLBACK_ENTER), "\r")
        self.assertIsNone(callback_input(CALLBACK_EXIT))


if __name__ == "__main__":
    unittest.main()
