
import random


def TestRandomStop():
    count = 0
    while True:
        count += 1
        a = random.random()
        if (a < 0.03):
            break

    print(count)
    return count


def TestStruct():
    import struct

    d = struct.pack("i", 10) + b'good'

    s = struct.unpack("i", d)
    print(s)


# TestStruct()


def TestInput():
    for e in range(3):
        s = input('hello\n')
        print(s)

import threading

t = threading.Thread(target=TestInput)
t.start()
t.join()