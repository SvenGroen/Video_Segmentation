import json
import os
import re
from collections import defaultdict
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd
import torch

"""
Extracts the evaluation results from all metrics.pth.tar files in a directory of trained models and displays
"""
def strip_base(x):
    """
    removes "base" from label string
    """
    if x == "base":
        return x
    else:
        return x.lstrip("base ")

def get_change(current, previous):
    """
    calculates the percentage change
    :param current: current value
    :param previous: base value
    :return: change of current to previous in percentage
    """
    if current == previous:
        return 0
    try:
        return ((current - previous) / previous) * 100.0
    except ZeroDivisionError:
        return float('inf')


def autolabel(rects, ax, percentage=True, base=None):
    """Attach a text label above each bar in *rects*, displaying its height."""
    for rect in rects:
        height = rect.get_height()
        if percentage:
            text = '{}%'.format(round(height * 100, 2))
        else:
            text = '{}'.format(height)
        if base is not None:
            change = get_change(height, base)
            if change == 0:
                text = '{}%'.format(height * 100)
            else:
                text = '{:+}'.format(round(change, 2)) + "%"

        ax.annotate(text,
                    xy=(rect.get_x() + rect.get_width() / 2, height),
                    xytext=(0, 3),  # 3 points vertical offset
                    textcoords="offset points",
                    size=35,
                    ha='center', va='bottom')


# path where the models are saved
model_path = Path("src/models/trained_models/yt_fullV4_probably_use")
out_name= "Metric_Results"
(model_path / out_name).mkdir(parents=True, exist_ok=True)

results = []
for folder in model_path.glob("*"):
    # Exclude certain models like this: if "lstmV6" in str(folder) or "V5" in str(folder)
    if "Metric" in str(folder) or "V6" in str(folder) or "V5" in str(folder) or "V7" in str(folder):
        continue
    if not os.path.isdir(folder):
        continue

    print("Processing: ", folder)
    metric_results = torch.load(folder / "final_results_prob_use/metrics.pth.tar", map_location="cpu")#"final_results_best_val/metrics.pth.tar"
    with open(folder / "train_config.json") as js:
        config = json.load(js)

    # create a label for better readability in the graphs
    pattern = re.search("V[1-9](_[1-9])?", config["model"])
    label = "base"
    if "lstm" in config["model"]:
        label += " + LSTM"
    if "gru" in config["model"]:
        label += " + GRU"
    if pattern:
        label += pattern.group(0)

    for i in ["train", "val"]:
        metric_results[i][-1]["Label"] = label
        metric_results[i][-1]["Model"] = str(config["model"]) + "_" + str(config["track_ID"])
        metric_results[i][-1]["model_class"] = "mobile" if "mobile" in str(config["model"]) else "resnet"

    results.append(metric_results)
# create pandas dataframe and extract the last metric results from the last evaluation.
dfs = []
for mode in ["train", "val"]:
    data = defaultdict(list)
    for i, category in enumerate(results[0][mode][-1].keys()):
        for model in results:
            if category not in ["curr_epoch", "hist"]:
                if isinstance(model[mode][-1][category], str):
                    data[category].append(model[mode][-1][category])
                elif torch.is_tensor(model[mode][-1][category].avg):
                    data[category].append(model[mode][-1][category].avg.item())
                else:
                    data[category].append(model[mode][-1][category].avg)
    df = pd.DataFrame.from_dict(data)
    df["Mode"] = mode
    dfs.append(df)
    df = df.sort_values(by="Label")
    df["Label"] = df["Label"].map(lambda x: strip_base(x))



    mobile_df = df[df["model_class"] == "mobile"].sort_values(by=["Label"])
    resnet_df = df[df["model_class"] != "mobile"].sort_values(by=["Label"])

    metrics = ["Mean IoU", "Pixel Accuracy", "Per Class Accuracy", "Dice", "FIP",
               "FP"]
    plots = []
    fontdict = {'fontsize': 30,
                'fontweight': 1,
                'verticalalignment': 'baseline',
                'horizontalalignment': "center"}

    # create one Matplot figure with multiple bar char
    tmp = [(0, 0), (0, 1), (1, 0), (1, 1)]
    for name, df in [("mobile", mobile_df), ("resnet", resnet_df)]:  # ,
        (model_path / out_name / name).mkdir(parents=True, exist_ok=True)
        f, ax = plt.subplots(2, 3, figsize=(50, 20))
        for pos, category in zip(tmp, metrics):
            ax[pos].set_ylim([0, 1])
            ax[pos].bar(df["Label"], df[category])
            ax[pos].axhline(y=float(df[category][df["Label"] == "base"]), xmin=-0, xmax=1, color="r")
            ax[pos].set_title(category, fontdict=fontdict)
            f.savefig(model_path / out_name / name / str(name + "_" + mode + ".png"))
        plt.close(fig=f)
    bars = []
    # create individual bar plots with more details
    for name, df in [("mobile", mobile_df), ("resnet", resnet_df)]:
        df = df.round(4).reset_index().sort_values(by="Label")
        df= pd.concat([df.iloc[[8], :], df.drop(8, axis=0)], axis=0)
        print(df["Label"])
        for category in metrics:
            base_performance = float(df[category][df["Label"] == "base"])
            f_new, ax_new = plt.subplots(figsize=(50, 20))
            bar = ax_new.bar(df["Label"], df[category])
            ax_new.axhline(y=base_performance, xmin=-0, xmax=1, color="r")
            ax_new.set_ylim([0, 1])
            ax_new.set_title(category, fontdict=fontdict)
            autolabel(bar, ax=ax_new, base=base_performance)  # , base=base_performance
            plt.xticks(fontsize=30)
            plt.yticks(fontsize=30)
            f_new.savefig(model_path / out_name / name / str(category + "_" + mode + ".png"))

            plt.close(fig=f_new)

result = pd.concat(dfs)
result.round(4).to_csv(model_path / out_name / "metric_results.csv", sep=";")
result.round(4).reset_index().to_json(model_path / out_name / "metric_results.json")

# create latex tables based on pandas Dataframes (need to be adjusted)

train = result["Mode"] == "train"
mobile = result["model_class"] == "mobile"
resnet = result["model_class"] == "resnet"
metrics = ["Mean IoU", "Dice", "Pixel Accuracy", "Per Class Accuracy"]
df_resnet = pd.DataFrame(result[resnet], columns=["Label", "Mode"] + metrics)
df_mobile = pd.DataFrame(result[mobile], columns=["Label", "Mode"] + metrics)
df_resnet[metrics] = df_resnet[metrics] * 100
df_mobile[metrics] = df_mobile[metrics] * 100
df_mobile = df_mobile.set_index(["Label", "Mode"]).unstack()
df_resnet = df_resnet.set_index(["Label", "Mode"]).unstack()
print(df_mobile.round(2).to_latex(index=True, multirow=True, multicolumn=True))
print(df_resnet.round(2).to_latex(index=True, multirow=True, multicolumn=True))

df_param = pd.DataFrame(result[train & mobile], columns=["Label", "model_class", "num_params"])
df_param["percentage"] = df_param["num_params"].pct_change()
df_param2 = pd.DataFrame(result[train & resnet], columns=["Label", "model_class", "num_params"])
df_param2["percentage"] = df_param2["num_params"].pct_change()
df_param = pd.concat([df_param, df_param2])
df_param = df_param.set_index(["Label", 'model_class']).unstack()
print(df_param.round(4).to_latex(index=True, multirow=True, multicolumn=True))

result["Time_taken"] = result["Time_taken"] * 100
df_time = pd.DataFrame(result[train & mobile], columns=["Label", "model_class", "Time_taken"])
df_time["percentage"] = df_time["Time_taken"].pct_change()
df_time2 = pd.DataFrame(result[train & resnet], columns=["Label", "model_class", "Time_taken"])
df_time2["percentage"] = df_time2["Time_taken"].pct_change()
df_time = pd.concat([df_time, df_time2])
df_time = df_time.set_index(["Label", 'model_class']).unstack()
print(df_time.round(4).to_latex(index=True, multirow=True, multicolumn=True, float_format=lambda x: f"{x}ms"))
