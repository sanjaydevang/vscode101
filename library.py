import random

coin = random.choice(["head", "tail"])
print(coin)


cards = (["Ace", "King", "Queen", "Jack"])
random.shuffle(cards)
for card in cards:
    random.shuffle(cards)
    print(cards)

    import statistics

    print(statistics.mean([100,2345]))



    import sys

    try:
        print("hello my name is", sys.argv[1])
    except IndexError:
        print("give the argument")



    import cowsay
    cowsay.cow("hello my name is sanjay")

    if len(sys.argv) > 1:
        cowsay.cow("hello my name is", sys.argv[1])
        