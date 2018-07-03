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
for ii in np.flip(np.sort(LUT_array[:,0])[:],0):
    LUT[ii] = LUT_array[np.where(LUT_array == ii)[0][0],1:]

#For Z positions which have not been calibrated, approximate with
#a regression of known positions.
## ACTUATOR_FITS has key of actuators
ACTUATOR_FITS = {}
no_defined_actuators = np.shape(LUT_array)[1]-1
pos = np.sort(LUT_array[:,0])[:]
ac_array = np.zeros((np.shape(LUT_array)[0],no_defined_actuators))

ac_pos = np.zeros(no_defined_actuators)

count = 0
for ii in pos:
    ac_array[count,:] = LUT_array[np.where(LUT_array == ii)[0][0],1:]
    count += 1

for ii in range(np.shape(pos)[0]):
    s, i, r, p, se = stats.linregress(pos, ac_array[:,ii])
    ACTUATOR_FITS[ii] = (s, i)

## This class handles classic Z-stack experiments.
class RemoteZStackExperiment(experiment.Experiment):
    ## Create the ActionTable needed to run the experiment. We simply move to
    # each Z-slice in turn, take an image, then move to the next.
    def generateActions(self):
        table = actionTable.ActionTable()
        curTime = 0
        prevAltitude = None
        numZSlices = int(math.ceil(self.zHeight / self.sliceHeight))
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
                for ii in range(no_defined_actuators):
                    (slope, intercept) = ACTUATOR_FITS[ii]
                    ac_pos[ii] = (slope * zTarget) + intercept

            motionTime, stabilizationTime = 0, 0
            if prevAltitude is not None:
                motionTime, stabilizationTime = self.zPositioner.getMovementTime(prevAltitude, zTarget)
            curTime += motionTime
            table.addAction(curTime, self.zPositioner, zTarget)
            curTime += stabilizationTime
            prevAltitude = zTarget

            # Image the sample.
            for cameras, lightTimePairs in self.exposureSettings:
                curTime = self.expose(curTime, cameras, lightTimePairs, table)
                # Advance the time very slightly so that all exposures
                # are strictly ordered.
                curTime += decimal.Decimal('1e-10')
            # Hold the Z motion flat during the exposure.
            table.addAction(curTime, self.zPositioner, zTarget)

        # Move back to the start so we're ready for the next rep.
        motionTime, stabilizationTime = self.zPositioner.getMovementTime(
                self.zHeight, 0)
        curTime += motionTime
        table.addAction(curTime, self.zPositioner, self.zStart)
        # Hold flat for the stabilization time, and any time needed for
        # the cameras to be ready. Only needed if we're doing multiple
        # reps, so we can proceed immediately to the next one.
        cameraReadyTime = 0
        if self.numReps > 1:
            for cameras, lightTimePairs in self.exposureSettings:
                for camera in cameras:
                    cameraReadyTime = max(cameraReadyTime,
                            self.getTimeWhenCameraCanExpose(table, camera))
        table.addAction(max(curTime + stabilizationTime, cameraReadyTime),
                self.zPositioner, self.zStart)

        return table



## A consistent name to use to refer to the class itself.
EXPERIMENT_CLASS = RemoteZStackExperiment
