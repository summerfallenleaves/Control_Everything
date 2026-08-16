"""CGEvent 键盘输入用的 macOS 虚拟键码与修饰键标志。"""

# 虚拟键码（https://eastmanreference.com/complete-list-of-applescript-key-codes）
KEYCODES = {
    "a": 0, "s": 1, "d": 2, "f": 3, "h": 4, "g": 5, "z": 6, "x": 7,
    "c": 8, "v": 9, "b": 11, "q": 12, "w": 13, "e": 14, "r": 15,
    "y": 16, "t": 17, "1": 18, "2": 19, "3": 20, "4": 21, "6": 22,
    "5": 23, "=": 24, "9": 25, "7": 26, "-": 27, "8": 28, "0": 29,
    "]": 30, "o": 31, "u": 32, "[": 33, "i": 34, "p": 35,
    "return": 36, "enter": 36, "l": 37, "j": 38, "'": 39, "k": 40,
    ";": 41, ",": 43, "/": 44, "n": 45, "m": 46, ".": 47,
    "tab": 48, "space": 49, "`": 50, "backspace": 51, "delete": 51,
    "escape": 53, "esc": 53, "command": 55, "shift": 56, "capslock": 57,
    "option": 58, "alt": 58, "control": 59, "ctrl": 59, "fn": 63,
    "f1": 122, "f2": 120, "f3": 99, "f4": 118, "f5": 96, "f6": 97,
    "f7": 98, "f8": 100, "f9": 101, "f10": 109, "f11": 103, "f12": 111,
    "home": 115, "end": 119, "pageup": 116, "pagedown": 121,
    "up": 126, "down": 125, "left": 123, "right": 124,
}

# CGEvent modifier flags
MODIFIER_FLAGS = {
    "command": 0x100000,  # kCGEventFlagMaskCommand
    "shift": 0x20000,     # kCGEventFlagMaskShift
    "option": 0x80000,    # kCGEventFlagMaskAlternate
    "alt": 0x80000,
    "control": 0x40000,   # kCGEventFlagMaskControl
    "ctrl": 0x40000,
    "caps": 0x10000,      # kCGEventFlagMaskCapsLock
}
