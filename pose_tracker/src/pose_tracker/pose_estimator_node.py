#!/usr/bin/env python

import roslib
roslib.load_manifest('pose_tracker')
import rospy
from rospy import (logdebug, loginfo, logwarn)

from pandas import Series

from func_utils import error_handler as eh
import param_utils as pu
import pose_learner as pl

import kinect.nite_skeleton_msg_utils as nsku

# Import message types
from pose_msgs.msg import PoseEstimated
from pose_tracker.srv import DatasetInfo
import kinect.msg as kin

DEFAULT_NAME = 'pose_estimator'
PARAMS = ('estimator_file', 'dataset_columns', 'drop_columns', 'labels')


class PoseEstimatorNode(object):

    """Class that builds the node."""

    def __init__(self, **kwargs):
        """
        Constructor.

        @keyword node_name: The name of the node.
        """
        self.node_name = kwargs.get('node_name', DEFAULT_NAME)
        rospy.init_node(self.node_name)
        rospy.on_shutdown(self.shutdown)
        rospy.loginfo("Initializing " + self.node_name + " node...")

        with eh(action=self.shutdown):
            self.load_parameters()

        # Subscriber
        rospy.Subscriber("skeletons", kin.NiteSkeletonList, self.skeleton_cb)

        # Publishers
        self.publisher = rospy.Publisher('pose_estimated', PoseEstimated)

    def load_parameters(self):
        """
        Load the parameters needed by the node.

        The node acquires new attribs with the name of the loaded params
        """
        try:
            params = pu.get_parameters(PARAMS)
            for p in params:
                pname = p.name.rsplit('/', 1)[-1]  # Get rid of param namespace
                setattr(self, pname, p.value)
        except:
            rospy.logfatal("Couldn't load Parameters: {}".format(list(params)))
            raise

    def load_estimator(self, filename=None):
        """
        Load an estimator from file.

        @param filename: the file name of the file storing the estimator
                         Default: self.estimator_file
        @type filename: string
        @return: the estimator loaded from the file"""
        if not filename:
            filename = self.estimator_file
        self.estimator = pl.load_clf(filename)
        return self.estimator

    def predict(self, instance):
        """
        Predict the output for an instance.

        @TODO: fill this method
        """
        return self.estimator.predict(instance)

    def predict_proba(self, instance):
        """Return prediction probabilities."""
        return self.estimator.predict_proba(instance)

    def _unpack_skeleton_msg(self, skel_msg):
        """Convert a NiteskeletonMsg to a list to a pandas.Series."""
        unpacked = list(nsku.unpack_skeleton_msg(skel_msg)[1])
        cols = self.dataset_columns
        return Series(unpacked, index=cols).drop(self.drop_columns, axis=1)

    def _build_pose_estimated_msg(self, skels):
        """Build a L{PoseEstimated} message from a L{Skeleton msg}."""
        epose = PoseEstimated()
        epose.raw_instance = self._unpack_skeleton_msg(skels.skeletons[0])
        epose.predicted_label_id = self.predict(epose.raw_instance)
        epose.predicted_label = self.labels[epose.predicted_label_id]
        epose.label_names = self.labels
        epose.label_probas = self.predict_proba(epose.raw_instance)
        return epose

    def skeleton_cb(self, skels):
        """Callback for skeleton messages."""
        with eh(logger=logwarn, low_msg='Could not estimate pose. '):
            pe_msg = self._build_pose_estimated_msg(skels)
            self.publisher.publish(pe_msg)

    def get_dataset_info(self):
        """Service client to get the dataset information used for learning."""
        rospy.wait_for_service('dataset_info')
        with eh(loginfo, log_msg="Service call failed: ",
                errors=rospy.ServiceException):
            dinfo = rospy.ServiceProxy('dataset_info', DatasetInfo)
            response = dinfo()
            return response.filename, response.columns, response.labels

    def run(self):
        """Run the node until shutdown."""
        while not rospy.is_shutdown():
            rospy.spin()

    def shutdown(self):
        """Close the node."""
        rospy.loginfo('Shutting down ' + rospy.get_name() + ' node')


if __name__ == '__main__':
    try:
        PoseEstimatorNode().run()
    except rospy.ROSInterruptException:
        pass
