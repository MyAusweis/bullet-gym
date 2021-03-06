from pybulletgym.gym_forward_walkers import PybulletHumanoid
#from Pybullet.scene_abstract import cpp_household
import numpy as np
import os

class PybulletHumanoidFlagrun(PybulletHumanoid):
	random_yaw = True

	def create_single_player_scene(self):
		s = PybulletHumanoid.create_single_player_scene(self)
		s.zero_at_running_strip_start_line = False
		return s

	def robot_specific_reset(self):
		PybulletHumanoid.robot_specific_reset(self)
		self.flag_reposition()

	def flag_reposition(self):
		self.walk_target_x = self.np_random.uniform(low=-self.scene.stadium_halflen,   high=+self.scene.stadium_halflen)
		self.walk_target_y = self.np_random.uniform(low=-self.scene.stadium_halfwidth, high=+self.scene.stadium_halfwidth)
		more_compact = 0.5  # set to 1.0 whole football field
		self.walk_target_x *= more_compact
		self.walk_target_y *= more_compact
		self.flag = None
		self.flag = self.scene.cpp_world.debug_sphere(self.walk_target_x, self.walk_target_y, 0.2, 0.2, 0xFF8080)
		self.flag_timeout = 200

	def calc_state(self):
		self.flag_timeout -= 1
		state = PybulletHumanoid.calc_state(self)
		if self.walk_target_dist < 1 or self.flag_timeout <= 0:
			self.flag_reposition()
			state = PybulletHumanoid.calc_state(self)  # caclulate state again, against new flag pos
			self.potential = self.calc_potential()	   # avoid reward jump
		return state

class PybulletHumanoidFlagrunHarder(PybulletHumanoidFlagrun):
	random_lean = True  # can fall on start

	def __init__(self):
		PybulletHumanoidFlagrun.__init__(self)
		self.electricity_cost /= 4   # don't care that much about electricity, just stand up!

	def robot_specific_reset(self):
		PybulletHumanoidFlagrun.robot_specific_reset(self)
		cpose = cpp_household.Pose()
		cpose.set_rpy(0, 0, 0)
		cpose.set_xyz(-1.5, 0, 0.05)
		self.aggresive_cube = self.scene.cpp_world.load_urdf(os.path.join(os.path.dirname(__file__), "models_household/cube.urdf"), cpose, False)
		self.on_ground_frame_counter = 0
		self.crawl_start_potential = None
		self.crawl_ignored_potential = 0.0
		self.initial_z = 0.8

	def alive_bonus(self, z, pitch):
		if self.frame%30==0 and self.frame>100 and self.on_ground_frame_counter==0:
			target_xyz  = np.array(self.body_xyz)
			robot_speed = np.array(self.robot_body.speed())
			angle	   = self.np_random.uniform(low=-3.14, high=3.14)
			from_dist   = 4.0
			attack_speed   = self.np_random.uniform(low=20.0, high=30.0)  # speed 20..30 (* mass in cube.urdf = impulse)
			time_to_travel = from_dist / attack_speed
			target_xyz += robot_speed*time_to_travel  # predict future position at the moment the cube hits the robot
			cpose = cpp_household.Pose()
			cpose.set_xyz(
				target_xyz[0] + from_dist*np.cos(angle),
				target_xyz[1] + from_dist*np.sin(angle),
				target_xyz[2] + 1.0)
			attack_speed_vector  = target_xyz - np.array(cpose.xyz())
			attack_speed_vector *= attack_speed / np.linalg.norm(attack_speed_vector)
			attack_speed_vector += self.np_random.uniform(low=-1.0, high=+1.0, size=(3,))
			self.aggresive_cube.set_pose_and_speed(cpose, *attack_speed_vector)
		if z < 0.8:
			self.on_ground_frame_counter += 1
		elif self.on_ground_frame_counter > 0:
			self.on_ground_frame_counter -= 1
		# End episode if the robot can't get up in 170 frames, to save computation and decorrelate observations.
		return self.potential_leak() if self.on_ground_frame_counter<170 else -1

	def potential_leak(self):
		z = self.body_xyz[2]		  # 0.00 .. 0.8 .. 1.05 normal walk, 1.2 when jumping
		z = np.clip(z, 0, 0.8)
		return z/0.8 + 1.0			# 1.00 .. 2.0

	def calc_potential(self):
		# We see alive bonus here as a leak from potential field. Value V(s) of a given state equals
		# potential, if it is topped up with gamma*potential every frame. Gamma is assumed 0.99.
		#
		# 2.0 alive bonus if z>0.8, potential is 200, leak gamma=0.99, (1-0.99)*200==2.0
		# 1.0 alive bonus on the ground z==0, potential is 100, leak (1-0.99)*100==1.0
		#
		# Why robot whould stand up: to receive 100 points in potential field difference.
		flag_running_progress = PybulletHumanoid.calc_potential(self)

		# This disables crawl.
		if self.body_xyz[2] < 0.8:
			if self.crawl_start_potential is None:
				self.crawl_start_potential = flag_running_progress - self.crawl_ignored_potential
				#print("CRAWL START %+0.1f %+0.1f" % (self.crawl_start_potential, flag_running_progress))
			self.crawl_ignored_potential = flag_running_progress - self.crawl_start_potential
			flag_running_progress  = self.crawl_start_potential
		else:
			#print("CRAWL STOP %+0.1f %+0.1f" % (self.crawl_ignored_potential, flag_running_progress))
			flag_running_progress -= self.crawl_ignored_potential
			self.crawl_start_potential = None

		return flag_running_progress + self.potential_leak()*100
