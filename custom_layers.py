import torch
import torch.nn as nn
import torch.nn.functional as F
import numpy as np
from torch.autograd import Variable
import torch 
import torch.nn as nn
import torchvision.datasets as dsets
import torchvision.transforms as transforms
from torch.autograd import Variable
from PIL import Image
import copy
from torch.nn.init import kaiming_normal, calculate_gain, normal


def _calculate_fan_in_and_fan_out(tensor):
    dimensions = tensor.ndimension()
    if dimensions < 2:
        raise ValueError("Fan in and fan out can not be computed for tensor with less than 2 dimensions")

    if dimensions == 2:  # Linear
        fan_in = tensor.size(1)
        fan_out = tensor.size(0)
    else:
        num_input_fmaps = tensor.size(1)
        num_output_fmaps = tensor.size(0)
        receptive_field_size = 1
        if tensor.dim() > 2:
            receptive_field_size = tensor[0][0].numel()
        fan_in = num_input_fmaps * receptive_field_size
        fan_out = num_output_fmaps * receptive_field_size

    return fan_in, fan_out

# same function as ConcatTable container in Torch7.
class ConcatTable(nn.Module):
    def __init__(self, layer1, layer2):
        super(ConcatTable, self).__init__()
        self.layer1 = layer1
        self.layer2 = layer2
        
    def forward(self,x):
        y = [self.layer1(x), self.layer2(x)]
        return y

class Flatten(nn.Module):
    def __init__(self):
        super(Flatten, self).__init__()

    def forward(self, x):
        return x.view(x.size(0), -1)



class fadein_layer(nn.Module):
    def __init__(self, config):
        super(fadein_layer, self).__init__()
        self.alpha = 0.0

    def update_alpha(self, delta):
        self.alpha = self.alpha + delta
        self.alpha = max(0, min(self.alpha, 1.0))

    def set_alpha(self, value):
        self.alpha = max(0, min(value, 1.0))

    # input : [x_low, x_high] from ConcatTable()
    def forward(self, x):
        return torch.add(x[0].mul(1.0-self.alpha), x[1].mul(self.alpha))



# https://github.com/github-pengge/PyTorch-progressive_growing_of_gans/blob/master/models/base_model.py
class minibatch_std_concat_layer(nn.Module):
    def __init__(self, averaging='all'):
        super(minibatch_std_concat_layer, self).__init__()
        self.averaging = averaging.lower()
        if 'group' in self.averaging:
            self.n = int(self.averaging[5:])
        else:
            assert self.averaging in ['all', 'flat', 'spatial', 'none', 'gpool'], 'Invalid averaging mode'%self.averaging
        self.adjusted_std = lambda x, **kwargs: torch.sqrt(torch.mean((x - torch.mean(x, **kwargs)) ** 2, **kwargs) + 1e-8)

    def forward(self, x):
        shape = list(x.size())
        self.n = min(self.n, shape[0])
        target_shape = copy.deepcopy(shape)
        vals = self.adjusted_std(x, dim=0, keepdim=True)
        if self.averaging == 'all':
            target_shape[1] = 1
            vals = torch.mean(vals, dim=1, keepdim=True)
        elif self.averaging == 'spatial':
            if len(shape) == 4:
                vals = mean(vals, axis=[2,3], keepdim=True)             # torch.mean(torch.mean(vals, 2, keepdim=True), 3, keepdim=True)
        elif self.averaging == 'none':
            target_shape = [target_shape[0]] + [s for s in target_shape[1:]]
        elif self.averaging == 'gpool':
            if len(shape) == 4:
                vals = mean(x, [0,2,3], keepdim=True)                   # torch.mean(torch.mean(torch.mean(x, 2, keepdim=True), 3, keepdim=True), 0, keepdim=True)
        elif self.averaging == 'flat':
            target_shape[1] = 1
            vals = torch.FloatTensor([self.adjusted_std(x)])
        else:                                                           # self.averaging == 'group'
            target_shape[1] = 1
            vals = x.view(self.n, -1, shape[1], shape[2], shape[3])  # GMCHW
            vals = vals - torch.mean(vals, dim=0, keepdim=True)  # GMCHW
            vals = torch.mean(vals**2, dim=0)  # MCHW
            vals = torch.sqrt(vals + 1e-8)  # MCHW
            vals = torch.mean(torch.mean(torch.mean(vals, dim=1), dim=1), dim=1)  # M
            vals = vals.view(-1, 1, 1, 1)  # M111
            vals = vals.repeat(self.n, 1, 1, 1)  # N111

            # target_shape[1] = self.n
            # vals = vals.view(self.n, self.shape[1]/self.n, self.shape[2], self.shape[3])
            # vals = mean(vals, axis=0, keepdim=True).view(1, self.n, 1, 1)
        vals = vals.expand(*target_shape)  # N1HW
        return torch.cat([x, vals], 1)

    def __repr__(self):
        return self.__class__.__name__ + '(averaging = %s)' % (self.averaging)


class pixelwise_norm_layer(nn.Module):
    def __init__(self):
        super(pixelwise_norm_layer, self).__init__()
        self.eps = 1e-8

    def forward(self, x):
        return x / (torch.mean(x**2, dim=1, keepdim=True) + self.eps) ** 0.5


# for equalized-learning rate.
class equalized_conv2d(nn.Module):
    def __init__(self, c_in, c_out, k_size, stride, pad, initializer='kaiming', bias=False, a=0.):
        super(equalized_conv2d, self).__init__()
        self.conv = nn.Conv2d(c_in, c_out, k_size, stride, pad, bias=False)
        if initializer == 'kaiming':    normal(self.conv.weight)
        fan_in, _ = _calculate_fan_in_and_fan_out(self.conv.weight)
        gain = (2. / (1. + a ** 2)) ** 0.5
        self.scale = gain / fan_in ** 0.5

        self.bias = torch.nn.Parameter(torch.FloatTensor(c_out).fill_(0))
        # if initializer == 'kaiming':    kaiming_normal(self.conv.weight, a=a)
        # elif initializer == 'xavier':   xavier_normal(self.conv.weight)

        # self.scale = (torch.mean(self.conv.weight.data ** 2)) ** 0.5  # Std.
        # self.conv.weight.data.copy_(self.conv.weight.data/self.scale)  # N(0, 1)

    def forward(self, x):
        x = self.conv(x.mul(self.scale))
        return x + self.bias.view(1,-1,1,1).expand_as(x)
        
 
class equalized_deconv2d(nn.Module):
    def __init__(self, c_in, c_out, k_size, stride, pad, initializer='kaiming'):
        super(equalized_deconv2d, self).__init__()
        self.deconv = nn.ConvTranspose2d(c_in, c_out, k_size, stride, pad, bias=False)
        if initializer == 'kaiming':    normal(self.deconv.weight)
        fan_in, _ = _calculate_fan_in_and_fan_out(self.deconv.weight)
        gain = (2. / (1. + 0. ** 2)) ** 0.5
        self.scale = gain / fan_in ** 0.5

        self.bias = torch.nn.Parameter(torch.FloatTensor(c_out).fill_(0))
        # if initializer == 'kaiming':    kaiming_normal(self.deconv.weight, a=0.)
        # elif initializer == 'xavier':   xavier_normal(self.deconv.weight)
        
        # deconv_w = self.deconv.weight.data.clone()
        # self.bias = torch.nn.Parameter(torch.FloatTensor(c_out).fill_(0))
        # self.scale = (torch.mean(self.deconv.weight.data ** 2)) ** 0.5
        # self.deconv.weight.data.copy_(self.deconv.weight.data/self.scale)
    def forward(self, x):
        x = self.deconv(x.mul(self.scale))
        return x + self.bias.view(1,-1,1,1).expand_as(x)


class View(nn.Module):
    def __init__(self, *shape):
        super(View, self).__init__()
        self.shape = shape
    def forward(self, input):
        return input.view(self.shape)


class equalized_linear(nn.Module):
    def __init__(self, c_in, c_out, initializer='kaiming', a=1., reshape=False):
        super(equalized_linear, self).__init__()
        self.linear = nn.Linear(c_in, c_out, bias=False)
        if initializer == 'kaiming':    normal(self.linear.weight)
        fan_in, _ = _calculate_fan_in_and_fan_out(self.linear.weight)
        gain = (2. / (1. + a ** 2)) ** 0.5
        self.scale = gain / fan_in ** 0.5

        if reshape:
            c_out /= 4 * 4
        self.bias = torch.nn.Parameter(torch.FloatTensor(c_out).fill_(0))
        # if initializer == 'kaiming':    kaiming_normal(self.linear.weight, a=a)
        # elif initializer == 'xavier':   torch.nn.init.xavier_normal(self.linear.weight)
        
        # self.bias = torch.nn.Parameter(torch.FloatTensor(c_out).fill_(0))
        # self.scale = (torch.mean(self.linear.weight.data ** 2)) ** 0.5
        # self.linear.weight.data.copy_(self.linear.weight.data/self.scale)

        self.reshape = reshape
        
    def forward(self, x):
        x = self.linear(x.mul(self.scale))
        if self.reshape:
            x = x.view(-1, 512, 4, 4)
            x = x + self.bias.view(1,-1, 1, 1).expand_as(x)
        else:
            x = x + self.bias.view(1,-1).expand_as(x)
        return x


# ref: https://github.com/github-pengge/PyTorch-progressive_growing_of_gans/blob/master/models/base_model.py
class generalized_drop_out(nn.Module):
    def __init__(self, mode='mul', strength=0.4, axes=(0,1), normalize=False):
        super(generalized_drop_out, self).__init__()
        self.mode = mode.lower()
        assert self.mode in ['mul', 'drop', 'prop'], 'Invalid GDropLayer mode'%mode
        self.strength = strength
        self.axes = [axes] if isinstance(axes, int) else list(axes)
        self.normalize = normalize
        self.gain = None

    def forward(self, x, deterministic=False):
        if deterministic or not self.strength:
            return x

        rnd_shape = [s if axis in self.axes else 1 for axis, s in enumerate(x.size())]  # [x.size(axis) for axis in self.axes]
        if self.mode == 'drop':
            p = 1 - self.strength
            rnd = np.random.binomial(1, p=p, size=rnd_shape) / p
        elif self.mode == 'mul':
            rnd = (1 + self.strength) ** np.random.normal(size=rnd_shape)
        else:
            coef = self.strength * x.size(1) ** 0.5
            rnd = np.random.normal(size=rnd_shape) * coef + 1

        if self.normalize:
            rnd = rnd / np.linalg.norm(rnd, keepdims=True)
        rnd = Variable(torch.from_numpy(rnd).type(x.data.type()))
        if x.is_cuda:
            rnd = rnd.cuda()
        return x * rnd

    def __repr__(self):
        param_str = '(mode = %s, strength = %s, axes = %s, normalize = %s)' % (self.mode, self.strength, self.axes, self.normalize)
        return self.__class__.__name__ + param_str



