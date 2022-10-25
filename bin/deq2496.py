#!/usr/bin/env python3

# Copyright (c) Rafael Sánchez

"""
    Usage: deq2496.py <cmd> [ <arg> ]

    Available commands and arguments:

            screen      rta | vu | peak | rotate
            contrast    3...9 | rotate
            get         state
            print       screen
            plot        screen
            restore                 (to deq2496.yml defaults)

"""
import sys
import os
import rtmidi
import mido
import yaml
import numpy as np
from   matplotlib import pyplot as plt

thisdir     = os.path.dirname( os.path.realpath(__file__) )

UHOME       = os.path.expanduser("~")
STATE_PATH  = f'{UHOME}/.deq2496'
CONFIG_PATH = f'{thisdir}/deq2496.yml'


wsv_table = {
    #   See write single value table at
    #   DEQ2496_MIDI_Implementation_V1_4.pdf
    #                   [modnr, lrmode, offset, datalen, data]

    'rta':                  [127, 0,  0, 1,  9],
    'rta_page3_fullscreen': [9,   0,  0, 1,  3],
    'rta_channel_l':        [9,   0,  1, 1,  0],
    'rta_channel_r':        [9,   0,  1, 1,  1],
    'rta_channel_l+r':      [9,   0,  1, 1,  2],
    'rta_max-5dB':          [9,   0,  2, 1,  1],
    'rta_range_60dB':       [9,   0,  4, 1,  2],
    'rta_rate_mid':         [9,   0,  9, 1,  1],
    'rta_peak_mid':         [9,   0, 10, 1,  2],

    'meter':                [127, 0,  0, 1, 12],
    'meter_page1_peak_rms': [12,  0,  0, 1,  1],
    'meter_page2_spl':      [12,  0,  0, 1,  2],
    'meter_page3_vumeter':  [12,  0,  0, 1,  3],

    'contrast_8':           [  8, 0,  1, 1,  8]
    }


def read_config():
    """ Read config from disk """
    try:
        with open(CONFIG_PATH, 'r') as f:
            cfg = yaml.safe_load(f.read())
    except:
       cfg = {'default': {'screen':'rta', 'contrast':9} }
    return cfg


def read_state():
    """ Read current state from disk """
    try:
        with open( STATE_PATH, 'r') as f:
            st = yaml.safe_load(f)
    except:
        st = {}
    return st


def save_state():
    """ Save state to disk """
    try:
        with open( STATE_PATH, 'w') as f:
            yaml.safe_dump(STATE, f, default_flow_style=False)
        res = 'done'
    except Exception as e:
        res = str(e)
    return res


def get_midi_interface(devName):
    ifces = mido.get_output_names()
    result = ''
    for i in ifces:
        if devName in i:
            result = i
            break
    if result:
        return result
    else:
        raise Exception(f'No midi matching {devName}')


def send_SysEx(x):
    #print(x)
    deq_header = [0x00, 0x20, 0x32, 0x00, 0x12]
    msg = mido.Message('sysex', data=deq_header + x)
    OutPORT.send(msg)


def write_single_value(sv):
    #  0x22: write single value (see table)
    #  Format: 0xF0, 0x00, 0x20, 0x32, DeviceID, ModelID,
    #          0x22, modnr, lrmode, offset, datalen, data*, 0xF7
    #      modnr: number of module (0-12)
    #      lrmode: channel mode: dual mono or stereo (0,1)
    #      offset: offset to first value
    #      datalen: size of data* (1 or 2)
    #      data*: value
    #
    # sv must be a list: [modnr, lrmode, offset, datalen, data]
    sv = [0x22] + sv
    send_SysEx(sv)


def get_identity_device():
    # 0x01: identify device
    # Format: 0xF0, 0x00, 0x20, 0x32, DeviceID, ModelID, 0x01, 0xF7
    # Response: 0xF0, 0x00, 0x20, 0x32, 0x00, 0x12, 0x02, asciidata*, 0xF7
    # asciidata*: n ascii characters identifying the product and software version
    #             also a tail 0x00 char is includes at the end
    send_SysEx([0x01])
    ans = InPORT.receive().data[6:-1]  # data excludes 0xF0 head and 0xF7 tail
    result = ''
    for c in ans:
        result += chr(c)
    return result


def get_screen_dump():
    # Sample screen chunk to demonstrate how screendata[80*46]
    # is codified in 7 bits words:
    #
    # 320 x 80 dot-matrix LC display
    #
    #           /  w1  /  w2  /  w3  /  etc .....
    #           123456712345671234567
    #  w1: w2:
    #   15 127     ########################
    #   31 127    #########################
    #   19  72    #  ###  #      #
    #   19  73    #  ###  #  #######
    #   17   9    #   #   #  #######
    #   17   9    #   #   #  #######
    #   16   8    #       #      ###
    #   16   9    #       #  #######
    #   18  73    #  # #  #  #######
    #   18  73    #  # #  #  #######
    #   19  73    #  ###  #  #######
    #   19  72    #  ###  #      ###
    #   31 127    #########################
    #   31 127    #########################
    #   31 127    #########################
    #   31  31    #####  #####
    #   30  31    ####   #####
    #   31  31    #####  #####
    #   31  31    #####  #####
    #   31  31    #####  #####
    #   31  31    #####  #####
    #   15 126     ##########
    #    0   0

    # SysEx:
    # 0x76: request screen dump
    # Format: 0xF0, 0x00, 0x20, 0x32, DeviceID, ModelID, 0x76, 0xF7
    # Response: 0xF0, 0x00, 0x20, 0x32, 0x00, 0x12, 0x36, screendata[80*46], 0xF7

    send_SysEx([0x76])

    # Getting screendata[80*46]
    return InPORT.receive().data[6:]  # data excludes 0xF0 head and 0xF7 tail


def print_screen(scrdata):
    # Print to console
    for i in range(len(scrdata)):
        print( bin(scrdata[i])[2:].zfill(7).replace('0',' ').replace('1','#'),
               end='' )
        if (i+1) % 46 == 0:
            print()
    print()


def plot_screen(scrdata):
    # 320 x 80 dot-matrix LC display

    S = np.array([])
    for i in range(len(scrdata)):
        heptaPixString = bin(scrdata[i])[2:].zfill(7)
        heptaPixArr    = np.fromiter(heptaPixString, dtype=int)
        S = np.append( S, heptaPixArr )
    S = S.reshape(80, 322)

    plt.imshow(S)
    plt.show()


def show_screen(scr):
    global STATE

    if scr == 'rotate':
        # lets iterate
        curr_scr = STATE["screen"]
        scrs = ['rta', 'peak', 'vu']
        scr = scrs[ (scrs.index(curr_scr) + 1) % len(scrs) ]

    # a short name alias
    wsv = write_single_value

    if scr == 'rta':
        wsv( wsv_table['rta'] )
        wsv( wsv_table['rta_channel_l+r'] )
        wsv( wsv_table['rta_max-5dB'] )
        wsv( wsv_table['rta_range_60dB'] )
        wsv( wsv_table['rta_rate_mid'] )
        wsv( wsv_table['rta_peak_mid'] )
        wsv( wsv_table['rta_page3_fullscreen'] )

    elif scr == 'vu':
        wsv( wsv_table['meter'] )
        wsv( wsv_table['meter_page3_vumeter'] )

    elif scr == 'peak':
        wsv( wsv_table['meter'] )
        wsv( wsv_table['meter_page1_peak_rms'] )

    STATE["screen"] = scr
    print(scr)


def contrast(mode):
    """ contrast valid values: '0' ... '15', 'rotate'
    """
    global STATE

    if mode.isdigit():

        c = int(mode)

    elif mode == 'rotate':

        mini, maxi = CONFIG["contrast_min"], CONFIG["contrast_max"]
        mid = int((mini+maxi)/2)
        values = [mini, mid, maxi]

        curr_c  = STATE["contrast"]
        closest = min(values, key=lambda x:abs(x-curr_c))

        c = values[ (values.index(closest) + 1) % len(values) ]

    else:

        return

    ncontrast = wsv_table['contrast_8']
    ncontrast[-1] = c
    write_single_value( ncontrast )

    STATE["contrast"] = c


def restore():
    show_screen(     CONFIG["default"]["screen"]   )
    contrast   ( str(CONFIG["default"]["contrast"]) )


if __name__ == '__main__':

    CONFIG = read_config()

    STATE  = read_state()

    midi_dev = CONFIG["midi_device"]
    InPORT  = mido.open_input(  get_midi_interface( midi_dev ) )
    OutPORT = mido.open_output( get_midi_interface( midi_dev ) )


    # Read command line
    cmd = ''
    args = []
    if sys.argv[1:]:
        cmd = sys.argv[1]
        if sys.argv[2:]:
            args = sys.argv[2:]
    else:
        print(__doc__)

    # Parse command
    if cmd == 'restore':
        restore()

    elif cmd == 'screen':
        show_screen( args[0] )

    elif cmd == 'contrast':
        contrast( args[0] )

    elif cmd == 'get':
        if args[0] == 'state':
            id_dev = get_identity_device()
            STATE["identity_device"] = id_dev
            print(STATE)

    elif cmd == 'print':
        if args[0] == 'screen':
            print_screen( get_screen_dump() )

    elif cmd == 'plot':
        if args[0] == 'screen':
            plot_screen( get_screen_dump() )

    else:
        print(__doc__)
        sys.exit()

    save_state()

