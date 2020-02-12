#!/bin/bash
SELF_PATH=$(python -c "import os; print(os.path.realpath('${0%/*}'))")
echo BUILDER_PATH = ${SELF_PATH}

cd cssdm && python ${SELF_PATH}/build.py --mms-path $HOME/mmsource/ --sm-path $HOME/sourcemod/ --sm-bin-path $HOME/sourcemod-bin/ --hl2sdk-ep1 $HOME/hl2sdk-episode1/