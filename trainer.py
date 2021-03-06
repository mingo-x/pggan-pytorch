import dataloader as DL
from config import config
import network as net
from math import floor, ceil
import os, sys 
from parse import parse
import torch
import torchvision.transforms as transforms
from torch.autograd import Variable, grad
from torch.optim import Adam
from tqdm import tqdm
import tf_recorder as tensorboard
import utils as utils
import numpy as np
import monotonic
from torchsummary import summary
from PIL import Image
import pickle
import time


class trainer:
    def __init__(self, config):
        self.config = config
        if torch.cuda.is_available():
            self.use_cuda = True
            torch.set_default_tensor_type('torch.cuda.FloatTensor')
            tqdm.write('Using GPU.')
        else:
            self.use_cuda = False
            torch.set_default_tensor_type('torch.FloatTensor')
        
        self.nz = config.nz
        self.optimizer = config.optimizer

        self.minibatch_repeat = 4
        self.resl = 2         # we start from 2^2 = 4
        self.lr = config.lr
        self.eps_drift = config.eps_drift
        self.smoothing = config.smoothing
        self.max_resl = config.max_resl
        self.trns_tick = config.trns_tick
        self.stab_tick = config.stab_tick
        self.TICK = config.TICK
        self.globalIter = 0
        self.globalTick = 0
        self.kimgs = 0
        self.stack = 0
        self.epoch = 0
        self.fadein = {'gen':None, 'dis':None}
        self.complete = {'gen':0, 'dis':0}
        self.phase = 'init'
        self.flag_flush_gen = False
        self.flag_flush_dis = False
        self.flag_add_noise = self.config.flag_add_noise
        self.flag_add_drift = self.config.flag_add_drift
        self.flag_wgan = self.config.flag_wgan
        
        # network and cirterion
        self.G = net.Generator(config)
        self.Gs = net.Generator(config)
        self.D = net.Discriminator(config)
        self.mse = torch.nn.MSELoss()
        if self.use_cuda:
            self.mse = self.mse.cuda()
            torch.cuda.manual_seed(int(time.time()))
            if config.n_gpu==1:
                self.G = torch.nn.DataParallel(self.G).cuda(device=0)
                self.Gs = torch.nn.DataParallel(self.Gs).cuda(device=0)
                self.D = torch.nn.DataParallel(self.D).cuda(device=0)
            else:
                gpus = []
                for i  in range(config.n_gpu):
                    gpus.append(i)
                self.G = torch.nn.DataParallel(self.G, device_ids=gpus).cuda()
                self.D = torch.nn.DataParallel(self.D, device_ids=gpus).cuda()  

        self.gen_ckpt = config.gen_ckpt
        self.gs_ckpt = config.gs_ckpt
        self.dis_ckpt = config.dis_ckpt
        if self.gen_ckpt != '' and self.dis_ckpt != '':
            pattern = '{}gen_R{}_T{}.pth.tar'
            parsed = parse(pattern, self.gen_ckpt)
            restore_resl = int(parsed[1])
            restore_tick = int(parsed[2])
            # Restore the network structure.
            for resl in xrange(3, restore_resl+1):
                self.G.module.grow_network(resl)
                self.Gs.module.grow_network(resl)
                self.D.module.grow_network(resl)
                if resl < restore_resl:
                    self.G.module.flush_network()
                    self.Gs.module.flush_network()
                    self.D.module.flush_network()
                    
            # for _ in xrange(int(self.resl), restore_resl):
            #     self.lr = self.lr * float(self.config.lr_decay)
            print(
                "Restored resolution", restore_resl, 
                "Restored global tick", restore_tick, 
                "Restored learning rate", self.lr)
            self.resl = restore_resl
            self.globalTick = restore_tick
            # Restore the network setting.
            if self.resl != 2:
                self.phase = 'stab'

        # define tensors, ship model to cuda, and get dataloader.
        self.renew_everything()
        if self.gen_ckpt != '' and self.dis_ckpt != '':
            self.G.module.flush_network()
            self.Gs.module.flush_network()
            self.D.module.flush_network()

            self.globalIter = floor(self.globalTick * self.TICK / (self.loader.batchsize * self.minibatch_repeat))
            gen_ckpt = torch.load(self.gen_ckpt)
            gs_ckpt = torch.load(self.gs_ckpt)
            dis_ckpt = torch.load(self.dis_ckpt)
            self.opt_d.load_state_dict(dis_ckpt['optimizer'])
            self.opt_g.load_state_dict(gen_ckpt['optimizer'])
            print('Optimizer restored.')
            self.resl = gen_ckpt['resl']
            self.G.module.load_state_dict(gen_ckpt['state_dict'])
            self.Gs.module.load_state_dict(gs_ckpt['state_dict'])
            self.D.module.load_state_dict(dis_ckpt['state_dict'])
            print('Model weights restored.')
            
            gen_ckpt = None
            dis_ckpt = None
            gs_ckpt = None

        print ('Generator structure: ')
        print(self.G)
        print ('Discriminator structure: ')
        print(self.D)

        # tensorboard
        self.use_tb = config.use_tb
        if self.use_tb:
            self.tb = tensorboard.tf_recorder()
        

    def resl_scheduler(self):
        '''
        this function will schedule image resolution(self.resl) progressively.
        it should be called every iteration to ensure resl value is updated properly.
        step 1. (trns_tick) -> transition in both gen and dis.
        step 2. (stab_tick) -> stabilize.
        '''
        if floor(self.resl) != 2 :
            self.trns_tick = self.config.trns_tick
            self.stab_tick = self.config.stab_tick
        
        self.batchsize = self.loader.batchsize
        if self.phase == 'init':
            delta = 1.0/self.stab_tick
        else:
            delta = 1.0/(self.trns_tick+self.stab_tick)
        d_alpha = 1.0*self.batchsize*self.minibatch_repeat/self.trns_tick/self.TICK

        # update alpha if fade-in layer exist.
        if self.fadein['gen'] is not None and self.fadein['dis'] is not None:
            if self.resl%1.0 < (self.trns_tick)*delta:  # [0, 0.5)
                self.fadein['gen'].update_alpha(d_alpha)
                self.fadein['gs'].update_alpha(d_alpha)
                self.fadein['dis'].update_alpha(d_alpha)
                self.complete['gen'] = self.fadein['gen'].alpha*100
                self.complete['dis'] = self.fadein['dis'].alpha*100
                self.phase = 'trns'
            elif self.resl%1.0 >= self.trns_tick*delta and self.resl%1.0 <= (self.trns_tick+self.stab_tick)*delta and self.phase != 'final':  # [0.5, 1.)
                self.phase = 'stab'
            
        prev_kimgs = self.kimgs
        self.kimgs = self.kimgs + self.batchsize*self.minibatch_repeat
        if (self.kimgs%self.TICK) < (prev_kimgs%self.TICK):
            self.globalTick = self.globalTick + 1
            # increase linearly every tick, and grow network structure.
            prev_resl = floor(self.resl)
            self.resl += delta
            self.resl = max(2, min(10.5, self.resl))        # clamping, range: 4 ~ 1024

            # flush network.
            if self.flag_flush_gen and self.flag_flush_dis and self.resl%1.0 >= (self.trns_tick)*delta and prev_resl!=2:
                if self.fadein['gen'] is not None:
                    self.fadein['gen'].update_alpha(d_alpha)
                    self.fadein['gs'].update_alpha(d_alpha)
                    self.complete['gen'] = self.fadein['gen'].alpha*100
                self.flag_flush_gen = False
                self.G.module.flush_network()   # flush G
                print(self.G.module.model)
                self.Gs.module.flush_network()         # flush Gs
                self.fadein['gen'] = None
                self.fadein['gs'] = None
                self.complete['gen'] = 0.0

                if self.fadein['dis'] is not None:
                    self.fadein['dis'].update_alpha(d_alpha)
                    self.complete['dis'] = self.fadein['dis'].alpha*100
                self.flag_flush_dis = False
                self.D.module.flush_network()   # flush and,
                print(self.D.module.model)
                self.fadein['dis'] = None
                self.complete['dis'] = 0.0

                self.phase = 'stab'

            # grow network.
            if floor(self.resl) != prev_resl and floor(self.resl)<self.max_resl+1:
                self.lr = self.lr * float(self.config.lr_decay)
                self.G.module.grow_network(floor(self.resl))
                self.Gs.module.grow_network(floor(self.resl))
                self.D.module.grow_network(floor(self.resl))
                self.renew_everything()
                self.fadein['gen'] = self.G.module.model.fadein_block
                self.fadein['gs'] = self.Gs.module.model.fadein_block
                self.fadein['dis'] = self.D.module.model.fadein_block
                self.flag_flush_gen = True
                self.flag_flush_dis = True
                self.phase = 'trns'
                print(self.G.module.model)
                print(self.D.module.model)

            if floor(self.resl) >= self.max_resl and self.resl%1.0 >= self.trns_tick*delta:
                self.phase = 'final'
                self.resl = self.max_resl + self.trns_tick *delta

            
    def renew_everything(self):
        # renew dataloader.
        self.loader = DL.dataloader(config)
        self.loader.renew(min(floor(self.resl), self.max_resl))
        
        # define tensors
        self.z = torch.FloatTensor(self.loader.batchsize, self.nz)
        self.x = torch.FloatTensor(self.loader.batchsize, 3, self.loader.imsize, self.loader.imsize)
        self.x_tilde = torch.FloatTensor(self.loader.batchsize, 3, self.loader.imsize, self.loader.imsize)
        self.real_label = torch.FloatTensor(self.loader.batchsize, 1).fill_(1)
        self.fake_label = torch.FloatTensor(self.loader.batchsize, 1).fill_(0)

        # enable cuda
        if self.use_cuda:
            self.z = self.z.cuda()
            self.x = self.x.cuda()
            self.x_tilde = self.x.cuda()
            self.real_label = self.real_label.cuda()
            self.fake_label = self.fake_label.cuda()
            # torch.cuda.manual_seed(int(time.time()))

        # wrapping autograd Variable.
        self.x = Variable(self.x)
        self.x_tilde = Variable(self.x_tilde)
        self.z = Variable(self.z)
        self.real_label = Variable(self.real_label)
        self.fake_label = Variable(self.fake_label)
        
        # ship new model to cuda.
        if self.use_cuda:
            self.G = self.G.cuda()
            self.Gs = self.Gs.cuda()
            self.D = self.D.cuda()
        
        # optimizer
        betas = (self.config.beta1, self.config.beta2)
        if self.optimizer == 'adam':
            self.opt_g = Adam(filter(lambda p: p.requires_grad, self.G.parameters()), lr=self.lr, betas=betas, weight_decay=0.0)
            self.opt_d = Adam(filter(lambda p: p.requires_grad, self.D.parameters()), lr=self.lr, betas=betas, weight_decay=0.0)
        

    def feed_interpolated_input(self, x):
        if self.phase == 'trns' and floor(self.resl)>2 and floor(self.resl)<=self.max_resl:
            # Mirror augmentation.
            # mask = torch.FloatTensor(x.shape[0], 1, 1, 1)
            # mask.uniform_()
            # mask = mask.cuda() if self.use_cuda else mask
            # mask = mask.expand_as(x)
            # x = tf.where(mask < 0.5, x, tf.reverse(x, axis=[3]))
            alpha = self.complete['gen']/100.0
            transform = transforms.Compose( [   transforms.ToPILImage(),
                                                transforms.Resize(size=int(pow(2,floor(self.resl)-1)), interpolation=Image.BILINEAR),      # 0: nearest
                                                transforms.Resize(size=int(pow(2,floor(self.resl))), interpolation=0),      # 0: nearest
                                                transforms.ToTensor(),
                                            ] )
            x_low = x.clone().add(1).mul(0.5)
            for i in range(x_low.size(0)):
                x_low[i] = transform(x_low[i]).mul(2).add(-1)
            x = torch.add(x.mul(alpha), x_low.mul(1-alpha)) # interpolated_x

        if self.use_cuda:
            return x.cuda()
        else:
            return x



    def add_noise(self, x):
        # TODO: support more method of adding noise.
        if self.flag_add_noise==False:
            return x

        if hasattr(self, '_d_'):
            self._d_ = self._d_ * 0.9 + torch.mean(self.fx_tilde).data.item() * 0.1
        else:
            self._d_ = 0.0
        strength = 0.2 * max(0, self._d_ - 0.5)**2
        z = np.random.randn(*x.size()).astype(np.float32) * strength
        z = Variable(torch.from_numpy(z)).cuda() if self.use_cuda else Variable(torch.from_numpy(z))
        return x + z

    def mul_rowwise(self, a, b):
        s = a.size()
        return (a.view(s[0], -1) * b).view(s)

    def calc_gradient_penalty(self, real_data, fake_data, iwass_lambda):
        data_shape = real_data.size()
        alpha = torch.FloatTensor(real_data.size(0), 1)
        alpha.uniform_()
        alpha = alpha.cuda() if self.use_cuda else alpha

        interpolates = self.mul_rowwise(real_data.data, 1-alpha) + self.mul_rowwise(fake_data.data, alpha)

        # Upscale
        scale = int(2 ** self.max_resl / real_data.size(2))
        interpolates = interpolates.view(data_shape[0], data_shape[1], data_shape[2], 1, data_shape[3], 1)
        interpolates = interpolates.repeat(1, 1, 1, scale, 1, scale)
        interpolates = interpolates.view(data_shape[0], data_shape[1], data_shape[2]*scale, data_shape[3]*scale)

        if self.use_cuda:
            interpolates = interpolates.cuda()
        interpolates = Variable(interpolates, requires_grad=True)

        # Downscale
        d_interpolates = interpolates.view(data_shape[0], data_shape[1], data_shape[2], scale, data_shape[3], scale)
        d_interpolates = torch.mean(torch.mean(d_interpolates, dim=5), dim=3)

        disc_interpolates = self.D(d_interpolates)
        mixed_loss = torch.sum(disc_interpolates)

        # gradients = grad(outputs=disc_interpolates, inputs=interpolates,
        #     grad_outputs=torch.ones(disc_interpolates.size()).cuda() if self.use_cuda else torch.ones(
        #         disc_interpolates.size()), create_graph=True, retain_graph=True, only_inputs=True)[0]

        gradients = grad(outputs=mixed_loss, inputs=interpolates,
            grad_outputs=torch.ones(mixed_loss.size()).cuda() if self.use_cuda else torch.ones(
                mixed_loss.size()), create_graph=True, retain_graph=True, only_inputs=True)[0]
        
        gradients = gradients.view(gradients.size(0), -1)
        mixed_norm = gradients.norm(2, dim=1)
        gradient_penalty = ((mixed_norm - 1) ** 2).mean() * iwass_lambda
        return gradient_penalty, torch.mean(disc_interpolates), torch.mean(mixed_norm)


    def train(self):
        # noise for test.
        self.z_test = torch.FloatTensor(self.loader.batchsize, self.nz)
        if self.use_cuda:
            self.z_test = self.z_test.cuda()
        self.z_test = Variable(self.z_test, volatile=True)
        self.z_test.data.resize_(self.loader.batchsize, self.nz).normal_(0.0, 1.0)

        # summary(self.G.module.model, input_size=(512, ))
        # summary(self.D.module.model, input_size=(3, 4, 4))
<<<<<<< HEAD
=======
        # exit()
>>>>>>> 70f249f1f09f20dcdc0d807fa8124fd44f1b6256

        net.soft_copy_param(self.Gs, self.G, 1.)
        x_test = self.G(self.z_test)
        Gs_test = self.Gs(self.z_test)
        os.system('mkdir -p repo/save/grid')
        utils.save_image_grid(x_test.data, 'repo/save/grid/{}_{}_G{}_D{}.png'.format(int(self.globalIter/self.config.save_img_every), self.phase, self.complete['gen'], self.complete['dis']), imsize=2**self.max_resl*4)
        utils.save_image_grid(Gs_test.data, 'repo/save/grid/{}_{}_G{}_D{}_Gs.png'.format(int(self.globalIter/self.config.save_img_every), self.phase, self.complete['gen'], self.complete['dis']), imsize=2**self.max_resl*4)
        
        for step in range(int(floor(self.resl)), self.max_resl+1+5):
            if self.phase == 'init':
                total_tick = self.stab_tick
                start_tick = self.globalTick
            else:
                total_tick = self.trns_tick + self.stab_tick
                start_tick = self.globalTick - (step - 2.5) * total_tick
                if step > self.max_resl:
                    start_tick = 0
            print('Start from tick', start_tick, 'till', total_tick)
            for iter in tqdm(range(int(start_tick) * self.TICK, (total_tick)*self.TICK, self.loader.batchsize*self.minibatch_repeat)):
                self.globalIter = self.globalIter+self.minibatch_repeat
                self.stack = self.stack + self.loader.batchsize*self.minibatch_repeat
                if self.stack > ceil(len(self.loader.dataset)):
                    self.epoch = self.epoch + 1
                    self.stack = int(self.stack%(ceil(len(self.loader.dataset))))

                # reslolution scheduler.
                self.resl_scheduler()
                
                for _ in range(self.minibatch_repeat):
                    # zero gradients.
                    self.G.zero_grad()
                    self.D.zero_grad()

                    # update discriminator.
                    batch = self.loader.get_batch()
                    self.x.data = self.feed_interpolated_input(batch)
                    if self.flag_add_noise:
                        self.x = self.add_noise(self.x)
                    self.z.data.resize_(self.loader.batchsize, self.nz).normal_(0.0, 1.0)
                    self.x_tilde = self.G(self.z)
                   
                    self.fx = self.D(self.x)
                    self.fx_tilde = self.D(self.x_tilde.detach())
                    real_score = torch.mean(self.fx)
                    fake_score = torch.mean(self.fx_tilde)
                    if self.flag_wgan:
                        loss_d_real = -self.fx + self.fx ** 2 * self.eps_drift
                        loss_d_fake = self.fx_tilde
                        gp, mixed_score, mixed_norm = self.calc_gradient_penalty(self.x, self.x_tilde.detach(), 10.)
                        loss_d = torch.mean(loss_d_real + loss_d_fake + gp)
                    else:
                        loss_d = self.mse(self.fx, self.real_label) + self.mse(self.fx_tilde, self.fake_label)

                    loss_d.backward()
                    self.opt_d.step()

                    net.soft_copy_param(self.Gs, self.G, 1-self.config.smoothing)

                    # update generator.
                    self.z.data.resize_(self.loader.batchsize, self.nz).normal_(0.0, 1.0)
                    self.x_tilde = self.G(self.z)
                    fx_tilde = self.D(self.x_tilde)
                    if self.flag_wgan:
                        loss_g = -torch.mean(fx_tilde)
                    else:
                        loss_g = self.mse(fx_tilde, self.real_label.detach())
                    loss_g.backward()
                    self.opt_g.step()
                    # logging.
                    log_msg = ' [E:{0}][T:{1}][{2:6}/{3:6}]  errD: {4:.4f} | errG: {5:.4f} | real_score: {12:.4f} | fake_score: {13:.4f} | mixed_score: {14:.4f} | mixed_norm: {15:.4f}| [lr:{11:.5f}][cur:{6:.3f}][resl:{7:4}][{8}][{9:.1f}%][{10:.1f}%]'.format(
                        self.epoch, self.globalTick, self.stack, len(self.loader.dataset), loss_d.data[0], loss_g.data[0], self.resl, int(pow(2,floor(self.resl))), self.phase, self.complete['gen'], self.complete['dis'], self.lr, real_score.data[0], fake_score.data[0], mixed_score.data[0], mixed_norm.data[0])
                    tqdm.write(log_msg)

                # save model.
                self.snapshot('repo/model')

                # save image grid.
                if self.globalIter%self.config.save_img_every == 0:
                    x_test = self.G(self.z_test)
                    Gs_test = self.Gs(self.z_test)
                    # os.system('mkdir -p repo/save/grid')
                    utils.save_image_grid(x_test.data, 'repo/save/grid/{}_{}_G{}_D{}.png'.format(int(self.globalIter/self.config.save_img_every), self.phase, self.complete['gen'], self.complete['dis']), imsize=2**self.max_resl*4)
                    utils.save_image_grid(self.x.data, 'repo/save/grid/{}_{}_G{}_D{}_x.png'.format(int(self.globalIter/self.config.save_img_every), self.phase, self.complete['gen'], self.complete['dis']), imsize=2**self.max_resl*4)
                    utils.save_image_grid(Gs_test.data, 'repo/save/grid/{}_{}_G{}_D{}_Gs.png'.format(int(self.globalIter/self.config.save_img_every), self.phase, self.complete['gen'], self.complete['dis']), imsize=2**self.max_resl*4)
                    # os.system('mkdir -p repo/save/resl_{}'.format(int(floor(self.resl))))
                    # utils.save_image_single(x_test.data, 'repo/save/resl_{}/{}_{}_G{}_D{}.jpg'.format(int(floor(self.resl)),int(self.globalIter/self.config.save_img_every), self.phase, self.complete['gen'], self.complete['dis']))

                # tensorboard visualization.
                if self.use_tb and self.globalIter%self.config.display_tb_every == 0:
                    # x_test = self.G(self.z_test)
                    self.tb.add_scalar('data/real_score', real_score.data[0], self.globalIter)
                    self.tb.add_scalar('data/fake_score', fake_score.data[0], self.globalIter)
                    self.tb.add_scalar('data/mixed_score', mixed_score.data[0], self.globalIter)
                    self.tb.add_scalar('data/mixed_norm', mixed_norm.data[0], self.globalIter)
                    self.tb.add_scalar('data/loss_g', loss_g.data[0], self.globalIter)
                    self.tb.add_scalar('data/loss_d', loss_d.data[0], self.globalIter)
                    self.tb.add_scalar('tick/lr', self.lr, self.globalIter)
                    self.tb.add_scalar('tick/cur_resl', int(pow(2,floor(self.resl))), self.globalIter)
                    # self.tb.add_image_grid('grid/x_test', 4, utils.adjust_dyn_range(x_test.data.float(), [-1,1], [0,1]), self.globalIter)
                    # self.tb.add_image_grid('grid/x_tilde', 4, utils.adjust_dyn_range(self.x_tilde.data.float(), [-1,1], [0,1]), self.globalIter)
                    # self.tb.add_image_grid('grid/x_intp', 4, utils.adjust_dyn_range(self.x.data.float(), [-1,1], [0,1]), self.globalIter)

            if self.phase == 'init':
                self.phase = 'stab'

    def get_state(self, target):
        if target == 'gen':
            state = {
                'resl' : self.resl,
                'state_dict' : self.G.module.state_dict(),
                'optimizer' : self.opt_g.state_dict(),
            }
            return state
        elif target == 'dis':
            state = {
                'resl' : self.resl,
                'state_dict' : self.D.module.state_dict(),
                'optimizer' : self.opt_d.state_dict(),
            }
            return state
        elif target == 'gs':
            state = {
                'resl' : self.resl,
                'state_dict' : self.Gs.module.state_dict(),
            }
            return state


    def snapshot(self, path):
        if not os.path.exists(path):
            os.system('mkdir -p {}'.format(path))
        # filename = 'R{}_T{}.pkl'.format(int(floor(self.resl)), self.globalTick)
        # file_path = os.path.join(path, filename)
        # if self.globalTick != 0 and self.globalTick%50==0:
        #     if self.phase == 'stab' or self.phase == 'final' or self.phase == 'init':
        #         with open(file_path, 'wb') as file:
        #             pickle.dump((self.G, self.Gs, self.D), file, protocol=pickle.HIGHEST_PROTOCOL)
        #         print('[snapshot] model saved @ {}'.format(file_path))
        # save every 100 tick if the network is in stab phase.
        ndis = 'dis_R{}_T{}.pth.tar'.format(int(floor(self.resl)), self.globalTick)
        ngen = 'gen_R{}_T{}.pth.tar'.format(int(floor(self.resl)), self.globalTick)
        ngs = 'gs_R{}_T{}.pth.tar'.format(int(floor(self.resl)), self.globalTick)
        if self.globalTick != 0 and self.globalTick%50==0:
            if self.phase == 'stab' or self.phase == 'final' or self.phase == 'init':
                save_path = os.path.join(path, ndis)
                # if not os.path.exists(save_path):
                torch.save(self.get_state('dis'), save_path)
                save_path = os.path.join(path, ngen)
                torch.save(self.get_state('gen'), save_path)
                save_path = os.path.join(path, ngs)
                torch.save(self.get_state('gs'), save_path)
                print('[snapshot] model saved @ {}'.format(path))


## perform training.
print '----------------- configuration -----------------'
for k, v in vars(config).items():
    print('  {}: {}').format(k, v)
print '-------------------------------------------------'
torch.backends.cudnn.benchmark = True           # boost speed.
trainer = trainer(config)
trainer.train()


