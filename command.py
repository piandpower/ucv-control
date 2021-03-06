# action
import math
import numpy as np
import StringIO
import PIL.Image
from random import randint
import time
import subprocess
import ucv_utils
import exceptions
from unrealcv import Client
import os

(HOST, PORT) = ('localhost', 9000)
sim_dir = '/home/mate/Documents/ucv-pkg2/LinuxNoEditor/unrealCVfirst/Binaries/Linux/'
sim_name = 'unrealCVfirst-Linux-Shipping'


class Commander:

    def __init__(self, number, mode=None):
        self.trajectory = []
        self.name = 'worker_' + str(number)

        # navigation goal direction
        self.goal_heading = 0
        self.goal_vector = [math.cos(math.radians(self.goal_heading)), math.sin(math.radians(self.goal_heading)), 0.0]

        # RL rewards
        self.goal_direction_reward = 1.0
        self.crash_reward = -10.0

        # Agent actions
        self.action_space = ('left', 'right', 'forward')  #  'backward'
        self.state_space_size = [84, 84, 3]  # for now RGB

        self.episode_finished = False
        self.should_terminate = False

        self.sim = None
        self.client = Client((HOST, PORT + number))
        self.should_stop = False
        self.mode = mode
        if self.mode == 'test':
            self.client.connect()
        else:
            self.start_sim()

    def shut_down(self):
        if self.client.isconnected():
            self.client.disconnect()
        if self.sim is not None:
            self.sim.terminate()
            self.sim = None

    def start_sim(self, restart=False):
        # disconnect and terminate if restarting
        attempt = 1
        got_connection = False
        while not got_connection and not self.should_stop:
            self.shut_down()
            print('Connection attempt: {}'.format(attempt))
            with open(os.devnull, 'w') as fp:
                self.sim = subprocess.Popen(sim_dir + sim_name, stdout=fp)
            attempt += 1
            time.sleep(10)
            port = self.client.message_client.endpoint[1]
            ucv_utils.set_port(port, sim_dir)
            self.client.connect()
            time.sleep(2)
            got_connection = self.client.isconnected()
            if got_connection:
                if restart:
                    try:
                        self.reset_agent()
                    except TypeError:
                        got_connection = False
            else:
                if attempt > 2:
                    wait_time = 20 + randint(5, 20)  # rand to avoid too many parallel sim startups
                    print('Multiple start attempts failed. Trying again in {} seconds.'.format(wait_time))
                    waited = 0
                    while not self.should_stop and (waited < wait_time):
                        time.sleep(1)
                        waited += 1
                    attempt = 1
        return

    def reconnect(self):
        print('{} trying to reconnect.'.format(self.name))
        self.client.disconnect()
        time.sleep(2)
        self.client.connect()
        return

    def action(self, cmd):
        angle = 20.0  # degrees/step
        speed = 20.0  # cm/step
        loc_cmd = [0.0, 0.0, 0.0]
        rot_cmd = [0.0, 0.0, 0.0]
        if cmd == 'left':
            # move(loc_cmd=speed, rot_cmd=[0, -angle, 0])
            loc_cmd[0] = speed
            rot_cmd[1] = -angle
        elif cmd == 'right':
            # move(loc_cmd=speed, rot_cmd=[0, angle, 0])
            loc_cmd[0] = speed
            rot_cmd[1] = angle
        elif cmd == 'forward':
            # move(loc_cmd=speed)
            loc_cmd[0] = speed
        elif cmd == 'backward':
            # move(loc_cmd=-speed)
            loc_cmd[0] = -speed

        reward = self.move(loc_cmd[0], rot_cmd)  # TODO: change this to full loc_cmd vector
        return reward

    def sim_command(self, cmd):
        if cmd == 'save_view':
            self.save_view()
        elif cmd == 'change_view':
            self.change_view()
        elif cmd == 'get_position':
            self.get_pos(print_pos=True)
        return

    def save_view(self):
        res = self.request('vget /viewmode')
        res2 = self.request('vget /camera/0/' + res)
        print(res2)
        return

    def change_view(self, viewmode=''):
        if viewmode == '':
            switch = dict(lit='normal', normal='depth', depth='object_mask', object_mask='lit')
            res = self.request('vget /viewmode')
            res2 = self.request('vset /viewmode ' + switch[res])
            # print(res2)
        elif viewmode in {'lit', 'normal', 'depth', 'object_mask'}:
            res2 = self.request('vset /viewmode ' + viewmode)
        return

    def get_pos(self, print_pos=False):

        if len(self.trajectory) == 0:
            rot = [float(v) for v in self.request('vget /camera/0/rotation').split(' ')]
            loc = [float(v) for v in self.request('vget /camera/0/location').split(' ')]
            self.trajectory.append(dict(location=loc, rotation=rot))
        else:
            loc = self.trajectory[-1]["location"]
            rot = self.trajectory[-1]["rotation"]

        if print_pos:
            print('Position x={} y={} z={}'.format(*loc))
            print('Rotation pitch={} heading={} roll={}'.format(*rot))

        return loc, rot

    def reset_agent(self):
        new_loc = self.trajectory[-1]["location"]
        new_rot = self.trajectory[-1]["rotation"]
        res1 = self.request('vset /camera/0/rotation {:.3f} {:.3f} {:.3f}'.format(*new_rot))
        assert res1
        res2 = self.request('vset /camera/0/moveto {:.2f} {:.2f} {:.2f}'.format(*new_loc))
        assert res2

        return

    def request(self, message):

        res = self.client.request(message)
        # if res in 'None', try restarting sim
        while not res:
            #self.start_sim(restart=True)
            print('[{}] sim error while trying to request {}'.format(self.name, message))
            self.reconnect()
            self.reset_agent()
            res = self.client.request(message)

        return res

    def move(self, loc_cmd=0.0, rot_cmd=(0.0, 0.0, 0.0)):
        loc, rot = self.get_pos()
        new_rot = [sum(x) % 360 for x in zip(rot, rot_cmd)]
        displacement = [loc_cmd * math.cos(math.radians(rot[1])), loc_cmd * math.sin(math.radians(rot[1])), 0.0]
        new_loc = [sum(x) for x in zip(loc, displacement)]
        collision = False

        if rot_cmd != (0.0, 0.0, 0.0):
            res = self.request('vset /camera/0/rotation {:.3f} {:.3f} {:.3f}'.format(*new_rot))
            assert(res == 'ok')
        if loc_cmd != 0.0:
            res = self.request('vset /camera/0/moveto {:.2f} {:.2f} {:.2f}'.format(*new_loc))
            if res != 'ok':
                collision = True
                new_loc = [float(v) for v in res.split(' ')]

        self.trajectory.append(dict(location=new_loc, rotation=new_rot))

        reward = self.calculate_reward(displacement=displacement, collision=collision)

        return reward

    def calculate_reward(self, displacement, collision=False):
        reward = 0
        distance = np.linalg.norm(np.array(displacement))
        if distance != 0:
            norm_displacement = np.array(displacement) / distance
            reward += np.dot(np.array(self.goal_vector), norm_displacement) * self.goal_direction_reward
        if collision:
            reward += self.crash_reward
            self.episode_finished = True

        # print('reward: {}'.format(reward))

        return reward

    @staticmethod
    def _read_npy(res):
        return np.load(StringIO.StringIO(res))

    @staticmethod
    def _read_png(res):
        img = PIL.Image.open(StringIO.StringIO(res))
        return np.asarray(img)

    def get_observation(self, grayscale=False, show=False):
        res = self.request('vget /camera/0/lit png')
        rgba = self._read_png(res)
        rgb = rgba[:, :, :3]
        if grayscale is True:
            observation = np.mean(rgb, 2)
        else:
            observation = rgb

        if show:
            img = PIL.Image.fromarray(observation)
            img.show()

        return observation

    def new_episode(self):
        # simple respawn: just turn around 180+/-60 deg
        self.move(rot_cmd=(0.0, randint(120, 240), 0.0))
        self.goal_heading = randint(0, 360)
        self.episode_finished = False
        return

    def is_episode_finished(self):
        return self.episode_finished

