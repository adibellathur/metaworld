import numpy as np

from metaworld.policies.action import Action
from metaworld.policies.policy import Policy, move


class SawyerReachV1Policy(Policy):

    @staticmethod
    def parse_obs(obs):
        return {
            'hand_xyz': obs[:3],
            'puck_xyz': obs[3:-3],
            'goal_vec': obs[-3:]
        }

    def get_action(self, obs):
        o_d = self.parse_obs(obs)

        action = Action({
            'delta_pos': np.arange(3),
            'grab_pow': 3
        })

        action['delta_pos'] = move(o_d['hand_xyz'], to_xyz=self.desired_xyz(o_d), p=5.)
        action['grab_pow'] = self.grab_pow(o_d)

        return action.array

    @staticmethod
    def desired_xyz(o_d):
        return o_d['hand_xyz'] + o_d['goal_vec']

    @staticmethod
    def grab_pow(o_d):
        return 0.
