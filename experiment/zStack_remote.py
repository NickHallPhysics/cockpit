from . import actionTable
from . import experiment

import decimal
import math
import numpy as np
import scipy.stats as stats

## Provided so the UI knows what to call this experiment.
EXPERIMENT_NAME = 'Remote Z-stack'

#Create accurate look up table for certain Z positions
##LUT dict has key of Z positions
LUT_array = np.loadtxt("remote_focus_LUT.txt")
LUT = {}
for ii in (LUT_array[:,0])[:]:
    LUT[ii] = LUT_array[np.where(LUT_array == ii)[0][0],1:]

## This class handles classic Z-stack experiments.
class RemoteZStackExperiment(experiment.Experiment):
    def __init__(self, dmHandler = None):
        self.dmHandler = dmHandler

        #For Z positions which have not been calibrated, approximate with
        #a regression of known positions.
        ## ACTUATOR_FITS has key of actuators
        self.no_defined_actuators = np.shape(LUT_array)[1]-1
        self.actuator_slopes = np.zeros(self.no_defined_actuators)
        self.actuator_intercepts = np.zeros(self.no_defined_actuators)

        pos = np.sort(LUT_array[:,0])[:]
        ac_array = np.zeros((np.shape(LUT_array)[0],self.no_defined_actuators))

        count = 0
        for ii in pos:
            ac_array[count,:] = LUT_array[np.where(LUT_array == ii)[0][0],1:]
            count += 1

        for ii in range(self.no_defined_actuators):
            s, i, r, p, se = stats.linregress(pos, ac_array[:,ii])
            self.actuator_slopes[ii] = s
            self.actuator_intercepts[ii] = i

    ## Create the ActionTable needed to run the experiment. We simply move to
    # each Z-slice in turn, take an image, then move to the next.
    def generateActions(self):
        table = actionTable.ActionTable()
        curTime = 0
        prevAltitude = None
        numZSlices = int(math.ceil(self.zHeight / self.sliceHeight))
        #Either call or calculate actuator positions for Z position
        try:
            self.ac_pos_start = LUT[self.zStart]
        except KeyError:
            self.ac_pos_start = (self.actuator_slopes * self.zStart) + self.actuator_intercepts
        if self.zHeight > 1e-6:
            # Non-2D experiment; tack on an extra image to hit the top of
            # the volume.
            numZSlices += 1
        for zIndex in range(numZSlices):
            # Move to the next position, then wait for the stage to
            # stabilize.
            zTarget = self.zStart + self.sliceHeight * zIndex

            #Either call or calculate actuator positions for Z position
            try:
                ac_pos = LUT[zTarget]
            except KeyError:
                ac_pos = (self.actuator_slopes * zTarget) + self.actuator_intercepts
            motionTime, stabilizationTime = 0, 0
            if prevAltitude is not None:
                motionTime, stabilizationTime = self.zPositioner.getMovementTime(prevAltitude, zTarget)
            curTime += motionTime
            #table.addAction(curTime, self.zPositioner, zTarget)
            if self.dmHandler is not None:
                table.addAction(curTime, self.dmHandler, ac_pos)
            curTime += stabilizationTime
            prevAltitude = zTarget

            # Image the sample.
            for cameras, lightTimePairs in self.exposureSettings:
                curTime = self.expose(curTime, cameras, lightTimePairs, table)
                # Advance the time very slightly so that all exposures
                # are strictly ordered.
                curTime += decimal.Decimal('1e-10')
            # Hold the Z motion flat during the exposure.
            #table.addAction(curTime, self.zPositioner, zTarget)
            if self.dmHandler is not None:
                table.addAction(curTime, self.dmHandler, ac_pos)

        # Move back to the start so we're ready for the next rep.
        motionTime, stabilizationTime = self.zPositioner.getMovementTime(
                self.zHeight, 0)
        curTime += motionTime
        #table.addAction(curTime, self.zPositioner, self.zStart)
        if self.dmHandler is not None:
            table.addAction(curTime, self.dmHandler, self.ac_pos_start)
        # Hold flat for the stabilization time, and any time needed for
        # the cameras to be ready. Only needed if we're doing multiple
        # reps, so we can proceed immediately to the next one.
        cameraReadyTime = 0
        if self.numReps > 1:
            for cameras, lightTimePairs in self.exposureSettings:
                for camera in cameras:
                    cameraReadyTime = max(cameraReadyTime,
                            self.getTimeWhenCameraCanExpose(table, camera))
        #table.addAction(max(curTime + stabilizationTime, cameraReadyTime),
        #        self.zPositioner, self.zStart)
        if self.dmHandler is not None:
            table.addAction(max(curTime + stabilizationTime, cameraReadyTime),
                        self.dmHandler, self.ac_pos_start)

        return table



## A consistent name to use to refer to the class itself.
EXPERIMENT_CLASS = RemoteZStackExperiment