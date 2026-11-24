<!-- Fictional source. Written for the mentat-wiki demo vault. Not a real article. -->

# Smoothing noisy elevation profiles

A fieldwork note from a fictional route-planning group.

GPS altitude is the least trustworthy number in a track. Between fixes it drifts by several metres,
and the drift is not random enough to cancel when summed. A flat walk can report 200 m of climbing
from noise alone.

The note compares raw cumulative gain with gain after a moving average over elevation. Smoothing
distance or time is a mistake: the x axis is exact enough, and changing it moves every gradient.

The window is a trade. Five points at a one-second interval remove most spikes and keep short climbs.
Fifteen points hide real steps on a staircase. Three passes over the same data flatten the profile
until it looks like a smoothing demo and not a hill.

Edges need padding. A moving average that starts at the second point loses the first and last
elevations, and on an out-and-back route the start and finish should match. Repeat the first and last
values before smoothing.

The second half of the note is about thresholds. Even a smooth profile wobbles by a metre or two, so
every wobble adds a little gain. Count a climb only after it passes a threshold. Three metres is a
reasonable start for day hikes; one metre keeps noise, five metres hides small rises.

Fictional. The numbers are illustrative, not measurements.
