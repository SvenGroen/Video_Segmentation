import glob
import random
import cv2
import numpy as np
from pathlib import Path
import os
import sys
sys.stderr.write("CWD: {}\n".format(os.getcwd()))
"""
Preprocessing step 1:
splits the Video files into 4 seconds snippets
"""

random.seed(12345)
np.random.seed(12345)
def add_noise(image):
    """
    add gausian noise
    :param image: image where noise is to be added
    :return: noisy image
    """
    row, col, ch = image.shape
    mean = 0
    # var = 0.1
    # sigma = var**0.5
    gauss = np.random.normal(mean, 1.5, (row, col, ch))
    gauss = gauss.reshape(row, col, ch)
    noisy = image + gauss
    return noisy

output_size = (int(2048 / 4), int(1080 / 4))
fps = 29
MAX_DURATION = 4

splits = ["train", "test"]

fourcc = cv2.VideoWriter_fourcc(*"mp4v")
for split in splits:
    vid_path = Path("src/dataset/data/videos/YT_originals") / split
    video_names = [vid.stem for vid in vid_path.glob("*")]

    out_path = Path("src/dataset/data/videos/YT_4sec") / split
    input_out_path = out_path / "input"
    input_out_path.mkdir(parents=True, exist_ok=True)
    i = 0
    video_counter = 0
    for vid in video_names:
        print("--------------------------------")
        print("video: ", vid)
        cap = cv2.VideoCapture(str(vid_path / vid) + ".mp4")
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        frame_rate = int(cap.get(cv2.CAP_PROP_FPS))
        cap.set(cv2.CAP_PROP_FPS, fps)
        start = True
        frame_counter = 0
        starter_frame = 0
        while cap.isOpened():
            ret, frame = cap.read()
            if ret:
                if start:
                    out_name = str(video_counter).zfill(5) + '.mp4'
                    out_input = cv2.VideoWriter(str(input_out_path / out_name),
                                                fourcc,
                                                fps, output_size)

                if starter_frame + MAX_DURATION * frame_rate == frame_counter:  # if 4 seconds passed break
                    video_counter += 1
                    starter_frame = frame_counter
                    if starter_frame + MAX_DURATION * frame_rate > total_frames:  # stop if last bit would not fit in 4 sec.
                        out_input.release()
                        break
                    out_name = str(video_counter).zfill(5) + '.mp4'
                    out_input = cv2.VideoWriter(str(input_out_path / out_name),
                                                fourcc,
                                                fps, output_size)
                start = False
                frame = cv2.resize(frame, output_size)
                out_input.write(np.uint8(frame))

                frame_counter += 1
            else:
                break
        cap.release()
        out_input.release()