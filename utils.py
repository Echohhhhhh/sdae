import os
import torch
import modules
import operator
import numpy as np
import torch.nn as nn
from functools import reduce
import matplotlib.pyplot as plt
from torchvision import transforms
from torch.utils.data import DataLoader
from torchvision.utils import save_image
from datasets import OlshausenDataset, MNISTVariant


def to_img(x):
    h = w = int(np.sqrt(
        reduce(operator.mul, list(x.size())[1:], 1)))
    x = x.view(x.size(0), 1, h, w)
    return x


def normalize(x):
    return (x - x.min()) / (x.max() - x.min())


def zero_mask(x, zero_frac):
    """Apply zero-masking noise to a PyTorch tensor.
    Returns noisy X and a bitmask describing the affected locations."""
    bitmask = torch.rand_like(x) > zero_frac  # approx. ZERO_FRAC zeros
    return x * bitmask.float(), bitmask  # assumes the minimum value is 0


def add_gaussian(x, gaussian_stdev):
    """Apply isotropic additive Gaussian noise to a PyTorch tensor.
    Returns noisy X and a bitmask describing the affected locations."""
    noise = torch.empty_like(x).normal_(0, gaussian_stdev)
    return x + noise, torch.ones_like(x, dtype=torch.uint8)


def salt_and_pepper(x, sp_frac, minval=0.0, maxval=1.0):
    """Apply salt-and-pepper noise to a PyTorch tensor.
    Returns noisy X and a bitmask describing the affected locations."""
    rand = torch.rand_like(x)
    min_idxs = rand < (sp_frac / 2.0)
    max_idxs = rand > (1.0 - sp_frac / 2.0)
    x_sp = x.clone()
    x_sp[min_idxs] = minval
    x_sp[max_idxs] = maxval
    return x_sp, torch.clamp(min_idxs + max_idxs, 0, 1)


def plot_first_layer_weights(model, weight_h=None, weight_w=None, block_on_viz=False):
    weights = model.get_first_layer_weights()
    print('shape of first-layer weights: %r' % (weights.shape,))

    if not block_on_viz:
        plt.ion()
        plt.show()

    fig, ax = plt.subplots(nrows=5, ncols=10)
    i = 0
    for row in ax:
        for col in row:
            weight = weights[i, :]
            if not weight_h or not weight_w:
                # Infer height and width of weight, assuming it is square
                weight_h = weight_w = int(np.sqrt(weight.size))
            col.imshow(np.reshape(weights[i, :], (weight_h, weight_w)), cmap='gray')
            col.axis('off')
            i += 1

    if not block_on_viz:
        plt.pause(10)
        plt.close()
    else:
        plt.show()


def save_image_wrapper(img, filepath):
    save_image(img, filepath)
    print('[o] saved image to %s' % filepath)


def init_model(model_class, restore_path, restore_required, **model_kwargs):
    # instantiate model
    model = getattr(modules, model_class)(**model_kwargs).cuda()
    print('instantiated a model of type %s' % model.__class__.__name__)
    # restore parameters
    if restore_required or restore_path:
        if restore_required or os.path.exists(restore_path):
            model.load_state_dict(torch.load(restore_path))
            print('restored "%s" model from %s' % (model_class, restore_path))
        else:
            print('warning: checkpoint %s not found, skipping...' % restore_path)
    return model


def init_loss(loss_type, **loss_kwargs):
    Loss = {
        'mse': nn.MSELoss,
        'bce': nn.BCELoss,
        'binary_cross_entropy': nn.BCELoss,
        'nll': nn.NLLLoss,
        'vae': modules.VAELoss,
    }[loss_type.lower()]
    print('using %r as the loss' % (Loss,))
    return Loss(**loss_kwargs)


def init_data_loader(dataset_key,
                     train_ver=True,
                     batch_size=128,
                     olshausen_path=None,
                     olshausen_step_size=1):

    dataset_key = dataset_key.lower()
    if dataset_key.startswith('mnist') \
            or dataset_key in MNISTVariant.variant_options:
        # MNIST or MNIST variant
        img_transform = transforms.Compose([
            transforms.ToTensor(),
            transforms.Lambda(normalize),
        ])
        variant = None if dataset_key == 'mnist' else dataset_key
        dataset = MNISTVariant('./data',
                               train=train_ver,
                               transform=img_transform,
                               download=True,
                               variant=variant)
        sample_h, sample_w = 28, 28
        data_minval, data_maxval = 0.0, 1.0
    elif dataset_key.startswith('olshausen'):
        # Olshausen natural scenes
        dataset = OlshausenDataset(olshausen_path,
                                   patch_size=12,
                                   step_size=olshausen_step_size,
                                   normalize=False)
        sample_h, sample_w = 12, 12
        data_minval = dataset.get_minval()
        data_maxval = dataset.get_maxval()
    else:
        raise ValueError('unrecognized dataset: %s' % dataset_key)
    data_loader = DataLoader(dataset, batch_size, shuffle=True)
    return data_loader, sample_h, sample_w, data_minval, data_maxval