#!/bin/sh
echo > ./bot-0.log
echo > ./bot-1.log
echo > ./bot-2.log
echo > ./bot-3.log
rm -f ./replays/*.log ./replays/*.hlt

./halite -v --replay-directory replays/ --turn-limit 500 -vvv --width 64 --height 64 "python3 MyBot.py" "python3 MyBot.py" 
# "python3 MyBot.py" "python3 MyBot.py"
# --seed 1542619241