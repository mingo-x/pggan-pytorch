import os
import torch
import numpy as np
from io import BytesIO
import scipy.misc
#import tensorflow as tf
import torchvision
import torchvision.transforms as transforms
from torch.utils.data import DataLoader
from torchvision.datasets import ImageFolder
from torch.autograd import Variable
from matplotlib import pyplot as plt
from PIL import Image
import monotonic


class dataloader:
    def __init__(self, config):
        self.root = config.train_data_root
        self.batch_table = {4:128, 8:128, 16:128, 32:64, 64:32, 128:16, 256:8, 512:4, 1024:4} # change this according to available gpu memory.
        self.batchsize = int(self.batch_table[pow(2,2)])        # we start from 2^2=4
        self.imsize = int(pow(2,2))
        self.num_workers = {4:16, 8:16, 16:16, 32:8, 64:8, 128:4, 256:4, 512:4, 1024:4}
        
    def renew(self, resl):
        print('[*] Renew dataloader configuration, load data from {}.'.format(self.root))
        
        self.batchsize = int(self.batch_table[pow(2,resl)])
        self.imsize = int(pow(2,resl))
        self.dataset = ImageFolder(
                    root=self.root,
                    transform=transforms.Compose(   [
                                                    transforms.Resize(size=(self.imsize,self.imsize), interpolation=Image.BILINEAR),
                                                    transforms.ToTensor(),
                                                    ]))       

        self.dataloader = DataLoader(
            dataset=self.dataset,
            batch_size=self.batchsize,
            shuffle=True,
            num_workers=self.num_workers[self.imsize],
            drop_last=True,
        )
        self.iter = iter(self.dataloader)

    def __iter__(self):
        return iter(self.dataloader)
    
    def __next__(self):
        return next(self.dataloader)

    def __len__(self):
        return len(self.dataloader.dataset)
       
    def get_batch(self):
        try:
            next_batch = self.iter.next()[0]
        except:
            self.iter = iter(self.dataloader)
            next_batch = self.iter.next()[0]
        next_batch = next_batch.mul(2).add(-1)         # pixel range [-1, 1]
        return next_batch


        









