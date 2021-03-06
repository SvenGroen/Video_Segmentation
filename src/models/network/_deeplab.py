import torch
from torch import nn
from torch.nn import functional as F
from src.models.recurrent_modules import ConvGRU, ConvLSTM
from src.models.network.utils import _SimpleSegmentationModel

__all__ = ["DeepLabV3"]

device = torch.device("cuda" if torch.cuda.is_available() else "cpu")


class DeepLabV3(_SimpleSegmentationModel):
    """
    Implements DeepLabV3 model from
    `"Rethinking Atrous Convolution for Semantic Image Segmentation"
    <https://arxiv.org/abs/1706.05587>`_.

    Arguments:
        backbone (nn.Module): the network used to compute the features for the model.
            The backbone should return an OrderedDict[Tensor], with the key being
            "out" for the last feature map used, and "aux" if an auxiliary classifier
            is used.
        classifier (nn.Module): module that takes the "out" element returned from
            the backbone and returns a dense prediction.
        aux_classifier (nn.Module, optional): auxiliary classifier used during training
    """
    pass


class DeepLabHeadV3PlusGRU(nn.Module):
    """
    Custom DeepLabV3Plus Head with an additional GRU unit.
    used for versions 3 and 4. Gru positioned after the encoder output and low level feature concatenation

    :param in_channels: number of input channels for the ASPP (vary across different backbones)
    :param low_level_channels: number of low level channels  (vary across different backbones)
    :param num_classes: number of output classes
    :param aspp_dilate: aspp dilatation rates
    :param store_previous: if True, t-2 and t-1 are used to help predict t, else only t is used
    """

    def __init__(self, in_channels, low_level_channels, num_classes, aspp_dilate=[12, 24, 36],
                 store_previous=False):
        """
        see help(DeepLabHeadV3PlusGRU) for detailed information
        """
        super(DeepLabHeadV3PlusGRU, self).__init__()
        self.project = nn.Sequential(
            nn.Conv2d(low_level_channels, 48, 1, bias=False),
            nn.BatchNorm2d(48),
            nn.ReLU(inplace=True),
        )

        self.aspp = ASPP(in_channels, aspp_dilate)
        self.classifier = nn.Sequential(
            nn.Conv2d(304, 256, 3, padding=1, bias=False),
            nn.BatchNorm2d(256),
            nn.ReLU(inplace=True),
            nn.Conv2d(256, num_classes, 1)
        )
        input_shape = (68, 128) if in_channels == 2048 else (67, 128)
        self._init_weight()
        self.gru = ConvGRU(input_size=input_shape, input_dim=304, hidden_dim=[304], kernel_size=(3, 3), num_layers=1,
                           dtype=torch.FloatTensor, batch_first=True, bias=True, return_all_layers=True)
        self.hidden = [None]
        self.store_previous = store_previous
        self.old_pred = [None, None]

    def forward(self, feature):
        """
        called after the backbone features are extracted.
        :param feature: backbone low and high level features
        :return: model output
        """
        low_level_feature = self.project(feature['low_level'])
        output_feature = self.aspp(feature['out'])
        output_feature = F.interpolate(output_feature, size=low_level_feature.shape[2:], mode='bilinear',
                                       align_corners=False)
        concat = torch.cat([low_level_feature, output_feature], dim=1)
        out = concat.unsqueeze(1)

        # store previous predictions to be used by gru
        if self.store_previous:
            if None in self.old_pred:
                for i in range(len(self.old_pred)):
                    self.old_pred[i] = torch.zeros_like(out)
            out = torch.cat(self.old_pred + [out], dim=1)
        out, self.hidden = self.gru(out, self.hidden[-1])
        self.hidden = [tuple(state.detach() for state in i) for i in self.hidden]
        out = out[0][:, -1, :, :, :].unsqueeze(1)
        if self.store_previous:
            # out = self.conv3d(out)
            self.old_pred[0] = self.old_pred[1]  # oldest at 0 position
            self.old_pred[1] = out.detach()  # newest at 1 position
        return self.classifier(out[:, -1, :, :, :])

    def _init_weight(self):
        """
        initialise weights
        """
        for m in self.modules():
            if isinstance(m, nn.Conv2d):
                nn.init.kaiming_normal_(m.weight)
            elif isinstance(m, (nn.BatchNorm2d, nn.GroupNorm)):
                nn.init.constant_(m.weight, 1)
                nn.init.constant_(m.bias, 0)


class DeepLabHeadV3PlusGRUV2(nn.Module):
    """
    Custom DeepLabV3Plus Head with an additional GRU unit0.
    used for versions 5 and 6. Gru positioned after the encoder output and low level feature concatenation.
    Reduced the number of channels through 1x1 convolutions before the GRU.

    :param in_channels: number of input channels for the ASPP (vary across different backbones)
    :param low_level_channels: number of low level channels  (vary across different backbones)
    :param num_classes: number of output classes
    :param aspp_dilate: aspp dilatation rates
    :param store_previous: if True, t-2 and t-1 are used to help predict t, else only t is used
    """

    def __init__(self, in_channels, low_level_channels, num_classes, aspp_dilate=[12, 24, 36], backbone="mobilenet",
                 store_previous=False):
        super(DeepLabHeadV3PlusGRUV2, self).__init__()
        self.project = nn.Sequential(
            nn.Conv2d(low_level_channels, 48, 1, bias=False),
            nn.BatchNorm2d(48),
            nn.ReLU(inplace=True),
        )

        self.aspp = ASPP(in_channels, aspp_dilate)
        self.conv_1x1_A = nn.Sequential(
            nn.Conv2d(304, int(304 / 2), 1, padding=0, stride=1, bias=False),
            nn.BatchNorm2d(int(304 / 2)),
            nn.ReLU(inplace=True),
        )
        self.conv_1x1_B = nn.Sequential(
            nn.Conv2d(304, int(304 / 2), 1, padding=0, stride=1, bias=False),
            nn.BatchNorm2d(int(304 / 2)),
            nn.ReLU(inplace=True),
        )
        self.classifier = nn.Sequential(
            nn.Conv2d(304, 256, 3, padding=1, bias=False),
            nn.BatchNorm2d(256),
            nn.ReLU(inplace=True),
            nn.Conv2d(256, num_classes, 1)
        )
        input_shape = (68, 128) if in_channels == 2048 else (67, 128)
        self._init_weight()
        self.gru = ConvGRU(input_size=input_shape, input_dim=int(304 / 2), hidden_dim=[int(304 / 2)],
                           kernel_size=(3, 3), num_layers=1,
                           dtype=torch.FloatTensor, batch_first=True, bias=True, return_all_layers=True)
        self.hidden = [None]
        self.store_previous = store_previous
        self.old_pred = [None, None]

    def forward(self, feature):
        """
        called after the backbone features are extracted.

        :param feature: backbone low and high level features
        :return: model output
        """
        low_level_feature = self.project(feature['low_level'])
        output_feature = self.aspp(feature['out'])
        output_feature = F.interpolate(output_feature, size=low_level_feature.shape[2:], mode='bilinear',
                                       align_corners=False)
        out = torch.cat([low_level_feature, output_feature], dim=1)
        out_A = self.conv_1x1_A(out)
        out_B = self.conv_1x1_B(out)
        out_A = out_A.unsqueeze(1)
        if self.store_previous:
            if None in self.old_pred:
                for i in range(len(self.old_pred)):
                    self.old_pred[i] = torch.zeros_like(out_A)
            out_A = torch.cat(self.old_pred + [out_A], dim=1)

        out_A, self.hidden = self.gru(out_A, self.hidden[-1])
        self.hidden = [tuple(state.detach() for state in i) for i in self.hidden]
        out_A = out_A[0][:, -1, :, :, :]
        out_A = out_A.unsqueeze(1)
        if self.store_previous:
            self.old_pred[0] = self.old_pred[1]  # oldest at 0 position
            self.old_pred[1] = out_A.detach()  # newest at 1 position
        out_A = out_A[:, -1, :, :, :]
        out = torch.cat([out_A, out_B], dim=1)
        return self.classifier(out)

    def _init_weight(self):
        """
        initialise weights
        """
        for m in self.modules():
            if isinstance(m, nn.Conv2d):
                nn.init.kaiming_normal_(m.weight)
            elif isinstance(m, (nn.BatchNorm2d, nn.GroupNorm)):
                nn.init.constant_(m.weight, 1)
                nn.init.constant_(m.bias, 0)


class DeepLabHeadV3PlusLSTM(nn.Module):
    """
    Custom DeepLabV3Plus Head with an additional LSTM unit.
    used for versions 3 and 4. LSTM positioned after the encoder output and low level feature concatenation

    :param in_channels: number of input channels for the ASPP (vary across different backbones)
    :param low_level_channels: number of low level channels  (vary across different backbones)
    :param num_classes: number of output classes
    :param aspp_dilate: aspp dilatation rates
    :param store_previous: if True, t-2 and t-1 are used to help predict t, else only t is used
    """

    def __init__(self, in_channels, low_level_channels, num_classes, aspp_dilate=[12, 24, 36], store_previous=False):
        super(DeepLabHeadV3PlusLSTM, self).__init__()
        self.project = nn.Sequential(
            nn.Conv2d(low_level_channels, 48, 1, bias=False),
            nn.BatchNorm2d(48),
            nn.ReLU(inplace=True),
        )

        self.aspp = ASPP(in_channels, aspp_dilate)

        self.classifier = nn.Sequential(
            nn.Conv2d(304, 256, 3, padding=1, bias=False),
            nn.BatchNorm2d(256),
            nn.ReLU(inplace=True),
            nn.Conv2d(256, num_classes, 1)
        )
        self._init_weight()
        self.lstm = ConvLSTM(input_dim=304, hidden_dim=[304], kernel_size=(3, 3), num_layers=1, batch_first=True,
                             bias=True,
                             return_all_layers=False)
        self.hidden = None
        self.store_previous = store_previous
        self.old_pred = [None, None]

    def forward(self, feature):
        """
        called after the backbone features are extracted.

        :param feature: backbone low and high level features
        :return: model output
        """
        low_level_feature = self.project(feature['low_level'])
        output_feature = self.aspp(feature['out'])
        output_feature = F.interpolate(output_feature, size=low_level_feature.shape[2:], mode='bilinear',
                                       align_corners=False)
        concat = torch.cat([low_level_feature, output_feature], dim=1)
        out = concat.unsqueeze(1)
        if self.store_previous:
            if None in self.old_pred:
                for i in range(len(self.old_pred)):
                    self.old_pred[i] = torch.zeros_like(out)
            out = torch.cat(self.old_pred + [out], dim=1)

        out, self.hidden = self.lstm(out, self.hidden)
        self.hidden = [tuple(state.detach() for state in i) for i in self.hidden]
        out = out[0][:, -1, :, :, :].unsqueeze(1)
        if self.store_previous:
            # out = self.conv3d(out)
            self.old_pred[0] = self.old_pred[1]  # oldest at 0 position
            self.old_pred[1] = out.detach()  # newest at 1 position
        return self.classifier(out[:, -1, :, :, :])

    def _init_weight(self):
        """
        initialise weights
        """
        for m in self.modules():
            if isinstance(m, nn.Conv2d):
                nn.init.kaiming_normal_(m.weight)
            elif isinstance(m, (nn.BatchNorm2d, nn.GroupNorm)):
                nn.init.constant_(m.weight, 1)
                nn.init.constant_(m.bias, 0)


class DeepLabHeadV3PlusLSTMV2(nn.Module):
    """
    Custom DeepLabV3Plus Head with an additional LSTM unit.
    used for versions 5 and 6. Gru positioned after the encoder output and low level feature concatenation.
    Reduced the number of channels through 1x1 convolutions before the LSTM.

    :param in_channels: number of input channels for the ASPP (vary across different backbones)
    :param low_level_channels: number of low level channels  (vary across different backbones)
    :param num_classes: number of output classes
    :param aspp_dilate: aspp dilatation rates
    :param store_previous: if True, t-2 and t-1 are used to help predict t, else only t is used
    """

    def __init__(self, in_channels, low_level_channels, num_classes, aspp_dilate=[12, 24, 36], store_previous=False):
        super(DeepLabHeadV3PlusLSTMV2, self).__init__()
        self.project = nn.Sequential(
            nn.Conv2d(low_level_channels, 48, 1, bias=False),
            nn.BatchNorm2d(48),
            nn.ReLU(inplace=True),
        )

        self.aspp = ASPP(in_channels, aspp_dilate)

        self.classifier = nn.Sequential(
            nn.Conv2d(304, 256, 3, padding=1, bias=False),
            nn.BatchNorm2d(256),
            nn.ReLU(inplace=True),
            nn.Conv2d(256, num_classes, 1)
        )
        self.conv_1x1_A = nn.Sequential(
            nn.Conv2d(304, int(304 / 2), 1, padding=0, stride=1, bias=False),
            nn.BatchNorm2d(int(304 / 2)),
            nn.ReLU(inplace=True),
        )
        self.conv_1x1_B = nn.Sequential(
            nn.Conv2d(304, int(304 / 2), 1, padding=0, stride=1, bias=False),
            nn.BatchNorm2d(int(304 / 2)),
            nn.ReLU(inplace=True),
        )
        self._init_weight()
        self.lstm = ConvLSTM(input_dim=int(304 / 2), hidden_dim=[int(304 / 2)], kernel_size=(3, 3), num_layers=1,
                             batch_first=True,
                             bias=True,
                             return_all_layers=False)
        self.hidden = None
        self.store_previous = store_previous
        self.old_pred = [None, None]

    def forward(self, feature):
        """
        called after the backbone features are extracted.

        :param feature: backbone low and high level features
        :return: model output
        """
        low_level_feature = self.project(feature['low_level'])
        output_feature = self.aspp(feature['out'])
        output_feature = F.interpolate(output_feature, size=low_level_feature.shape[2:], mode='bilinear',
                                       align_corners=False)
        out = torch.cat([low_level_feature, output_feature], dim=1)
        out_A = self.conv_1x1_A(out)
        out_B = self.conv_1x1_B(out)
        out_A = out_A.unsqueeze(1)
        if self.store_previous:
            if None in self.old_pred:
                for i in range(len(self.old_pred)):
                    self.old_pred[i] = torch.zeros_like(out_A)
            out_A = torch.cat(self.old_pred + [out_A], dim=1)

        out_A, self.hidden = self.lstm(out_A, self.hidden)
        self.hidden = [tuple(state.detach() for state in i) for i in self.hidden]
        out_A = out_A[0][:, -1, :, :, :]
        out_A = out_A.unsqueeze(1)
        if self.store_previous:
            self.old_pred[0] = self.old_pred[1]  # oldest at 0 position
            self.old_pred[1] = out_A.detach()  # newest at 1 position
        out_A = out_A[:, -1, :, :, :]
        out = torch.cat([out_A, out_B], dim=1)
        return self.classifier(out)

    def _init_weight(self):
        """initialise weights"""
        for m in self.modules():
            if isinstance(m, nn.Conv2d):
                nn.init.kaiming_normal_(m.weight)
            elif isinstance(m, (nn.BatchNorm2d, nn.GroupNorm)):
                nn.init.constant_(m.weight, 1)
                nn.init.constant_(m.bias, 0)


class DeepLabHeadV3Plus(nn.Module):
    def __init__(self, in_channels, low_level_channels, num_classes, aspp_dilate=[12, 24, 36]):
        super(DeepLabHeadV3Plus, self).__init__()
        self.project = nn.Sequential(
            nn.Conv2d(low_level_channels, 48, 1, bias=False),
            nn.BatchNorm2d(48),
            nn.ReLU(inplace=True),
        )

        self.aspp = ASPP(in_channels, aspp_dilate)

        self.classifier = nn.Sequential(
            nn.Conv2d(304, 256, 3, padding=1, bias=False),
            nn.BatchNorm2d(256),
            nn.ReLU(inplace=True),
            nn.Conv2d(256, num_classes, 1)
        )
        self._init_weight()

    def forward(self, feature):
        low_level_feature = self.project(feature['low_level'])
        output_feature = self.aspp(feature['out'])
        output_feature = F.interpolate(output_feature, size=low_level_feature.shape[2:], mode='bilinear',
                                       align_corners=False)
        return self.classifier(torch.cat([low_level_feature, output_feature], dim=1))

    def _init_weight(self):
        for m in self.modules():
            if isinstance(m, nn.Conv2d):
                nn.init.kaiming_normal_(m.weight)
            elif isinstance(m, (nn.BatchNorm2d, nn.GroupNorm)):
                nn.init.constant_(m.weight, 1)
                nn.init.constant_(m.bias, 0)


class DeepLabHead(nn.Module):
    def __init__(self, in_channels, num_classes, aspp_dilate=[12, 24, 36]):
        super(DeepLabHead, self).__init__()

        self.classifier = nn.Sequential(
            ASPP(in_channels, aspp_dilate),
            nn.Conv2d(256, 256, 3, padding=1, bias=False),
            nn.BatchNorm2d(256),
            nn.ReLU(inplace=True),
            nn.Conv2d(256, num_classes, 1)
        )
        self._init_weight()

    def forward(self, feature):
        return self.classifier(feature['out'])

    def _init_weight(self):
        for m in self.modules():
            if isinstance(m, nn.Conv2d):
                nn.init.kaiming_normal_(m.weight)
            elif isinstance(m, (nn.BatchNorm2d, nn.GroupNorm)):
                nn.init.constant_(m.weight, 1)
                nn.init.constant_(m.bias, 0)


class AtrousSeparableConvolution(nn.Module):
    """ Atrous Separable Convolution
    """

    def __init__(self, in_channels, out_channels, kernel_size,
                 stride=1, padding=0, dilation=1, bias=True):
        super(AtrousSeparableConvolution, self).__init__()
        self.body = nn.Sequential(
            # Separable Conv
            nn.Conv2d(in_channels, in_channels, kernel_size=kernel_size, stride=stride, padding=padding,
                      dilation=dilation, bias=bias, groups=in_channels),
            # PointWise Conv
            nn.Conv2d(in_channels, out_channels, kernel_size=1, stride=1, padding=0, bias=bias),
        )

        self._init_weight()

    def forward(self, x):
        return self.body(x)

    def _init_weight(self):
        for m in self.modules():
            if isinstance(m, nn.Conv2d):
                nn.init.kaiming_normal_(m.weight)
            elif isinstance(m, (nn.BatchNorm2d, nn.GroupNorm)):
                nn.init.constant_(m.weight, 1)
                nn.init.constant_(m.bias, 0)


class ASPPConv(nn.Sequential):
    def __init__(self, in_channels, out_channels, dilation):
        modules = [
            nn.Conv2d(in_channels, out_channels, 3, padding=dilation, dilation=dilation, bias=False),
            nn.BatchNorm2d(out_channels),
            nn.ReLU(inplace=True)
        ]
        super(ASPPConv, self).__init__(*modules)


class ASPPPooling(nn.Sequential):
    def __init__(self, in_channels, out_channels):
        super(ASPPPooling, self).__init__(
            nn.AdaptiveAvgPool2d(1),
            nn.Conv2d(in_channels, out_channels, 1, bias=False),
            nn.BatchNorm2d(out_channels),
            nn.ReLU(inplace=True))

    def forward(self, x):
        size = x.shape[-2:]
        x = super(ASPPPooling, self).forward(x)
        return F.interpolate(x, size=size, mode='bilinear', align_corners=False)


class ASPP(nn.Module):
    def __init__(self, in_channels, atrous_rates):
        super(ASPP, self).__init__()
        out_channels = 256
        modules = []
        modules.append(nn.Sequential(
            nn.Conv2d(in_channels, out_channels, 1, bias=False),
            nn.BatchNorm2d(out_channels),
            nn.ReLU(inplace=True)))

        rate1, rate2, rate3 = tuple(atrous_rates)
        modules.append(ASPPConv(in_channels, out_channels, rate1))
        modules.append(ASPPConv(in_channels, out_channels, rate2))
        modules.append(ASPPConv(in_channels, out_channels, rate3))
        modules.append(ASPPPooling(in_channels, out_channels))

        self.convs = nn.ModuleList(modules)

        self.project = nn.Sequential(
            nn.Conv2d(5 * out_channels, out_channels, 1, bias=False),
            nn.BatchNorm2d(out_channels),
            nn.ReLU(inplace=True),
            nn.Dropout(0.1), )

    def forward(self, x):
        res = []
        for conv in self.convs:
            res.append(conv(x))
        res = torch.cat(res, dim=1)
        return self.project(res)


def convert_to_separable_conv(module):
    new_module = module
    if isinstance(module, nn.Conv2d) and module.kernel_size[0] > 1:
        new_module = AtrousSeparableConvolution(module.in_channels,
                                                module.out_channels,
                                                module.kernel_size,
                                                module.stride,
                                                module.padding,
                                                module.dilation,
                                                module.bias)
    for name, child in module.named_children():
        new_module.add_module(name, convert_to_separable_conv(child))
    return new_module
