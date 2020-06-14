import numpy as np
from gym.spaces import Box

from metaworld.envs.env_util import get_asset_full_path
from metaworld.envs.mujoco.sawyer_xyz.base import SawyerXYZEnv


class SawyerPushWallEnvV2(SawyerXYZEnv):

    def __init__(self, random_init=False):
        liftThresh = 0.04

        goal_low = (-0.05, 0.85, 0.05)
        goal_high = (0.05, 0.9, 0.3)
        hand_low = (-0.5, 0.40, 0.05)
        hand_high = (0.5, 1, 0.5)
        obj_low = (-0.05, 0.6, 0.015)
        obj_high = (0.05, 0.65, 0.015)

        super().__init__(
            self.model_name,
            hand_low=hand_low,
            hand_high=hand_high,
        )

        self.init_config = {
            'obj_init_angle': .3,
            'obj_init_pos': np.array([0, 0.6, 0.02]),
            'hand_init_pos': np.array([0, .6, .2]),
        }

        self.goal = np.array([0.05, 0.8, 0.015])

        self.obj_init_angle = self.init_config['obj_init_angle']
        self.obj_init_pos = self.init_config['obj_init_pos']
        self.hand_init_pos = self.init_config['hand_init_pos']

        self.random_init = random_init
        self.liftThresh = liftThresh
        self.max_path_length = 150

        self.action_space = Box(
            np.array([-1, -1, -1, -1]),
            np.array([1, 1, 1, 1]),
        )

        self.obj_and_goal_space = Box(
            np.hstack((obj_low, goal_low)),
            np.hstack((obj_high, goal_high)),
        )
        self.goal_space = Box(np.array(goal_low), np.array(goal_high))

        hand_to_goal_max = self.hand_high - np.array(goal_low)
        self.observation_space = Box(
            np.hstack((self.hand_low, obj_low, -hand_to_goal_max)),
            np.hstack((self.hand_high, obj_high, hand_to_goal_max)),
        )

        self.num_resets = 0
        self.reset()

    @property
    def model_name(self):
        return get_asset_full_path('sawyer_xyz/sawyer_push_wall_v2.xml')

    def step(self, action):
        self.set_xyz_action(action[:3])
        self.do_simulation([action[-1], -action[-1]])
        # The marker seems to get reset every time you do a simulation
        self._set_goal_marker(self._state_goal)
        ob = self._get_obs()
        obs_dict = self._get_obs_dict()
        # reward, _, reach_dist, _, push_dist, pickRew, _, placingDist = self.compute_reward(action, obs_dict)
        reward, reach_dist, push_dist = self.compute_reward(action, obs_dict)
        success = float(push_dist <= 0.07)

        info = {
            'reach_dist': reach_dist,
            'epRew': reward,
            'goalDist': push_dist,
            'success': success,
            'goal': self.goal
        }
        self.curr_path_length +=1
        return ob, reward, False, info

    def _get_obs(self):
        hand = self.get_endeff_pos()
        objPos =  self.data.get_geom_xpos('objGeom')
        hand_to_goal = self._state_goal - hand
        flat_obs = np.concatenate((hand, objPos, hand_to_goal))
        return np.concatenate([flat_obs,])

    def _get_obs_dict(self):
        return dict(
            state_observation=self._get_obs(),
            state_desired_goal=self._state_goal,
            state_achieved_goal=self.data.get_geom_xpos('objGeom'),
        )

    def _set_goal_marker(self, goal):
        # self.data.site_xpos[self.model.site_name2id('goal_{}'.format(self.task_type))] = (
        #     goal[:3]
        # )
        # for task_type in self.task_types:
        #     if task_type != self.task_type:
        #         self.data.site_xpos[self.model.site_name2id('goal_{}'.format(task_type))] = (
        #             np.array([10.0, 10.0, 10.0])
        #         )
        self.data.site_xpos[self.model.site_name2id('goal')] = goal[:3]

    def _set_obj_xyz(self, pos):
        qpos = self.data.qpos.flat.copy()
        qvel = self.data.qvel.flat.copy()
        qpos[9:12] = pos.copy()
        qvel[9:15] = 0
        self.set_state(qpos, qvel)

    def adjust_initObjPos(self, orig_init_pos):
        # This is to account for meshes for the geom and object are not aligned
        # If this is not done, the object could be initialized in an extreme position
        diff = self.get_body_com('obj')[:2] - self.data.get_geom_xpos('objGeom')[:2]
        adjustedPos = orig_init_pos[:2] + diff

        # The convention we follow is that body_com[2] is always 0, and geom_pos[2] is the object height
        return [adjustedPos[0], adjustedPos[1],self.data.get_geom_xpos('objGeom')[-1]]

    def reset_model(self):
        self._reset_hand()
        self._state_goal = self.goal.copy()
        self.obj_init_pos = self.adjust_initObjPos(self.init_config['obj_init_pos'])
        self.obj_init_angle = self.init_config['obj_init_angle']
        self.objHeight = self.data.get_geom_xpos('objGeom')[2]
        self.heightTarget = self.objHeight + self.liftThresh

        if self.random_init:
            goal_pos = np.random.uniform(
                self.obj_and_goal_space.low,
                self.obj_and_goal_space.high,
                size=(self.obj_and_goal_space.low.size),
            )
            self._state_goal = goal_pos[3:]
            while np.linalg.norm(goal_pos[:2] - self._state_goal[:2]) < 0.15:
                goal_pos = np.random.uniform(
                    self.obj_and_goal_space.low,
                    self.obj_and_goal_space.high,
                    size=(self.obj_and_goal_space.low.size),
                )
                self._state_goal = goal_pos[3:]
            self._state_goal = np.concatenate((goal_pos[-3:-1], [self.obj_init_pos[-1]]))
            self.obj_init_pos = np.concatenate((goal_pos[:2], [self.obj_init_pos[-1]]))

        self._set_goal_marker(self._state_goal)
        self._set_obj_xyz(self.obj_init_pos)
        self.maxpush_dist = np.linalg.norm(self.obj_init_pos[:2] - np.array(self._state_goal)[:2])
        self.target_reward = 1000*self.maxpush_dist + 1000*2
        self.num_resets += 1
        return self._get_obs()

    def _reset_hand(self):
        for _ in range(10):
            self.data.set_mocap_pos('mocap', self.hand_init_pos)
            self.data.set_mocap_quat('mocap', np.array([1, 0, 1, 0]))
            self.do_simulation([-1,1], self.frame_skip)
        rightFinger, leftFinger = self.get_site_pos('rightEndEffector'), self.get_site_pos('leftEndEffector')
        self.init_fingerCOM = (rightFinger + leftFinger)/2
        self.pickCompleted = False

    def compute_reward(self, actions, obs):
        obs = obs['state_observation']
        obj_pos = obs[3:6]
        rightFinger, leftFinger = self.get_site_pos('rightEndEffector'), self.get_site_pos('leftEndEffector')
        fingerCOM = (rightFinger + leftFinger) / 2

        goal = self._state_goal
        assert np.all(goal == self.get_site_pos('goal'))

        reach_dist = np.linalg.norm(fingerCOM - obj_pos)
        reach_rew = -reach_dist
        push_dist = np.linalg.norm(obj_pos[:2] - goal[:2])

        c1 = 1000
        c2 = 0.01
        c3 = 0.001

        if reach_dist < 0.05:
            push_rew = c1*(self.maxpush_dist - push_dist) + \
                       c1*(np.exp(-(push_dist**2)/c2) +
                           np.exp(-(push_dist**2)/c3))
            push_rew = max(push_rew, 0)
        else:
            push_rew = 0

        reward = reach_rew + push_rew
        return [reward, reach_dist, push_dist]