#!/usr/bin/env python
import roslib
roslib.load_manifest('pose_tracker')
import rospy
from rospy import (logdebug, loginfo, logwarn, logerr, logfatal)

# from operator import (gt, lt)
from collections import namedtuple
# import itertools as it
from itertools import cycle
import pandas as pd

from func_utils import error_handler as eh
from param_utils import load_params
import circular_dataframe as cdf

from pose_msgs.msg import (PoseInstance, JointVelocities)


class DatasetNotFullError(Exception):
    pass


def is_dataset_full(expected_len, dataset):
    if len(dataset) != expected_len:
        raise DatasetNotFullError()


def is_still(threshold, df):
    ''' Returns True if all joints in df are below threshold.
        Otherwise, returns False '''
    return df.lt(threshold).values.all()


def is_moving(threshold, df):
    ''' Returns True if all joints in df are equal or above threshold.
        Otherwise, returns False '''
    return df.gt(threshold).values.all()


# def next_caller(iterator):
#     return iterator.next(), iterator
_DEFAULT_NAME = 'instance_averager_node'
_NODE_PARAMS = ['dataframe_length', 'movement_threshold']

Detector = namedtuple('Detector', ['detector', 'publisher', 'msg'])


class PoseDetectorNode():

    ''' Node that receives L{JointVelocities} and evaluates them to
        publish wheter the user is moving or not.

        Publishes a L{PoseInstance} to /user_pose if the user L{is_still}
        Publishes a L{JointVelocities} to /user_moving if the user L{is_moving}
        Note that it only publishes if there has been a change

        Example:
        --------
            1. User is moving
            2. User stops. --> publication to /user_pose
            3. User keeps stoped.
            4. User starts moving --> publication to /user_moving
            5. User stops again --> publication to /user_pose
    '''

    def __init__(self, **kwargs):
        name = kwargs.get('node_name', _DEFAULT_NAME)
        rospy.init_node(name)
        self.node_name = rospy.get_name()
        rospy.on_shutdown(self.shutdown)
        loginfo("Initializing " + self.node_name + " node...")

        with eh(logger=logfatal, log_msg="Couldn't load parameters",
                reraise=True):
            self.dflen, self.threshold = load_params(_NODE_PARAMS)

        ### Publishers and Subscribers
        rospy.Subscriber(
            '/joint_velocities', JointVelocities, self.velocities_cb)
        rospy.Subscriber('/pose_instance', PoseInstance, self.instance_cb)
        self.__pose_pub = rospy.Publisher('/user_pose', PoseInstance)
        self.__moving_pub = rospy.Publisher('/user_moving', JointVelocities)

        self.velocities = pd.DataFrame()
        self.pose_instance = PoseInstance()

        # Detectors
        self._still_detector = \
            Detector(is_still, self.__pose_publisher, self.pose_instance)
        self._moving_detector = \
            Detector(is_moving, self.__velo_publisher, self.velocities)

        self.detectors = cycle([self._still_detector, self._moving_detector])
        self.current_detector = self.detectors.next()

    def instance_cb(self, msg):
        ''' Stores the latest received L{PoseInstance} message '''
        self.pose_instance = msg

    def velocities_cb(self, msg):
        new_instance = pd.Series(msg.velocities, index=msg.columns)
        self.velocities = cdf.append_instance(self.velocities, new_instance)
        try:
            is_dataset_full(self.df)
        except DatasetNotFullError:
            return
        if self.current_detector(self.threshold, self.velocities):
            self.change_detector()
            self.current_detector.publish(self.current_detector.msg)

    def __pose_publisher(self, pose_instance):
        ''' Helper method that publishes the las velocities instance from
            the L{PoseDetectorNode.velocities} DataFrame '''
        self.__pose_pub.publish(pose_instance)

    def __velo_publisher(self, velocities):
        ''' Helper method that publishes the las velocities instance from
            the L{PoseDetectorNode.velocities} DataFrame '''
        msg = JointVelocities(columns=velocities.columns,
                              velocities=velocities.iloc[-1].values)
        self.__moving_pub.publish(msg)

    def change_detector(self, detectors):
        ''' Updates current detector and flushes the velocities dataset '''
        self.current_detector = detectors.next()
        self.velocities = pd.DataFrame()

    def run(self):
        rospy.spin()

    def shutdown(self):
        ''' Closes the node '''
        loginfo('Shutting down ' + rospy.get_name() + ' node.')


if __name__ == '__main__':
    try:
        node = PoseDetectorNode()
        node.run()
    except rospy.ROSInterruptException:
        pass
