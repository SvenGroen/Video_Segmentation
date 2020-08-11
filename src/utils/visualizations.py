from collections import defaultdict
from pathlib import Path
import matplotlib.pyplot as plt
import numpy as np


def visualize_metric(metric_log, step_size=2, epoch=0, save_file_path=None):
    for key in metric_log["train"][0]:
        y = defaultdict(list)
        for i in range(len(metric_log["train"])):
            y["train"].append(metric_log["train"][i][key].avg)
            y["val"].append(metric_log["val"][i][key].avg)
        print(y["train"], y["test"])
        x = list(range(0, epoch + 1, step_size))
        plt.plot(x, y["train"], color='red', label="train")
        plt.plot(x, y["val"], color='blue', label="validation")
        plt.legend()
        plt.title('Average Train/Test {} score'.format(key))
        plt.xlabel('Epoch')
        plt.ylabel('Average {}'.format(key))
        plt.savefig(str(Path(save_file_path) / (key + ".jpg")))
        plt.close()


def visualize_logger(logger, path):
    def save_figure(values, y_label="", x_label="Epoch"):
        # saves values in a plot
        plt.plot(values)
        plt.xlabel(x_label)
        plt.ylabel(y_label)
        plt.savefig(path + "/" + y_label + "_" + x_label + ".jpg")
        plt.close()

    save_figure(logger["lrs"], y_label="Learning Rate")
    save_figure(logger["loss"], y_label="Loss")