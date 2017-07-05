# action
import math


class Commander:

    def __init__(self, client):
        self.client = client
        self.trajectory = []

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

        self.move(loc_cmd[0], rot_cmd)  # change this to full loc_cmd vector
        return

    def sim_command(self, cmd):
        if cmd == 'save_view':
            self.save_view()
        elif cmd == 'change_view':
            self.change_view()
        elif cmd == 'get_position':
            self.get_pos(print_pos=True)
        return

    def save_view(self):
        res = self.client.request('vget /viewmode')
        res2 = self.client.request('vget /camera/0/' + res)
        print(res2)
        return

    def change_view(self, viewmode=''):
        if viewmode == '':
            switch = dict(lit='normal', normal='depth', depth='object_mask', object_mask='lit')
            res = self.client.request('vget /viewmode')
            res2 = self.client.request('vset /viewmode ' + switch[res])
            # print(res2)
        elif viewmode in {'lit', 'normal', 'depth', 'object_mask'}:
            res2 = self.client.request('vset /viewmode ' + viewmode)
        return

    def get_pos(self, print_pos=False):

        if len(self.trajectory) == 0:
            rot = [float(v) for v in self.client.request('vget /camera/0/rotation').split(' ')]
            loc = [float(v) for v in self.client.request('vget /camera/0/location').split(' ')]
            self.trajectory.append(dict(location=loc, rotation=rot))
        else:
            loc = self.trajectory[-1]["location"]
            rot = self.trajectory[-1]["rotation"]

        if print_pos:
            print('Position x={} y={} z={}'.format(*loc))
            print('Rotation pitch={} heading={} roll={}'.format(*rot))

        return loc, rot

    def move(self, loc_cmd=(0.0, 0.0, 0.0), rot_cmd=(0.0, 0.0, 0.0)):
        loc, rot = self.get_pos()
        new_rot = [sum(x) for x in zip(rot, rot_cmd)]
        displacement = [loc_cmd * math.cos(math.radians(rot[1])), loc_cmd * math.sin(math.radians(rot[1])), 0.0]
        new_loc = [sum(x) for x in zip(loc, displacement)]
        collision = False

        if rot_cmd != (0.0, 0.0, 0.0):
            res = self.client.request('vset /camera/0/rotation {} {} {}'.format(*new_rot))
            assert res == 'ok', 'Fail to set camera rotation'
        if loc_cmd != 0.0:
            res = self.client.request('vset /camera/0/moveto {} {} {}'.format(*new_loc))
            print(res)
            if res != 'ok':
                print('Collision. Failed to move to position.')
                collision = True
                new_loc = [float(v) for v in res.split(' ')]

            self.trajectory.append(dict(location=new_loc, rotation=new_rot))

        # calculate_reward(goal_vector, displacement=displacement, collision=collision)
        return collision