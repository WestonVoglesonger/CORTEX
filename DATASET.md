# EEG Dataset for CORTEX Simulation 


## Subject Identifiers

This dataset was obtained via PhysioNet, where it is publicly available. It originates from a publication in the IEEE Trans BioMed Eng. academic journal.

**Paper**: [BCI2000: a general-purpose brain-computer interface (BCI) system](https://pubmed.ncbi.nlm.nih.gov/15188875/)

**Dataset:** [EEG Motor Movement/Imagery Dataset](https://physionet.org/content/eegmmidb/1.0.0/S001/#files-panel)

**Authors**: Gerwin Schalk 1, Dennis J McFarland, Thilo Hinterberger, Niels Birbaumer, Jonathan R Wolpaw

**Date published:** September 2009

**Journal**: IEEE Transactions on Biomedical Engineering (Volume 51, Issue 6, June 2004)

**Citation**: Schalk, G., McFarland, D.J., Hinterberger, T., Birbaumer, N., Wolpaw, J.R. BCI2000: A General-Purpose Brain-Computer Interface (BCI) System. IEEE Transactions on Biomedical Engineering 51(6):1034-1043, 2004.

**Abstract:** A set of 64-channel EEGs from subjects who performed a series of motor/imagery tasks. This data set consists of over 1500 one- and two-minute EEG recordings, obtained from 109 volunteers.

## Contextual Information
### Experiment

**License:** Open Data Commons Attribution 1.0 (ODC-By 1.0). 

* Subjects performed different motor/imagery tasks while 64-channel EEG were recorded using the BCI2000 system (http://www.bci2000.org).
* each subject performed a total of 14 experimental runs: Two one-minute baseline runs, one with eyes open and one with eyes closed, and three two-minute runs of each of the four following tasks:
    * A target appears on either the left or the right side of the screen. The subject opens and closes the corresponding fist until the target disappears. Then the subject relaxes.
    * A target appears on either the left or the right side of the screen. The subject **imagines** opening and closing the corresponding fist until the target disappears. Then the subject relaxes.
    * A target appears on either the top or the bottom of the screen. The subject opens and closes either both fists (if the target is on top) or both feet (if the target is on the bottom) until the target disappears. Then the subject relaxes.
    * A target appears on either the top or the bottom of the screen. The subject **imagines** opening and closing either both fists (if the target is on top) or both feet (if the target is on the bottom) until the target disappears. Then the subject relaxes.

### Data Collection
**Dataset Format:** EDF+

**Sampling Rate**: 160 Hz

**Channels**: 64 EEG + an annotation channel


## Selection (frozen for this project)
- **Subjects used**: `S001–S010`  _(adjust if you want a different fixed subset)_.
- **Sessions / runs**: **R03–R14** (motor/imagery tasks; three repeats of each of four tasks). We exclude R01–R02 (baselines) for now.
- **File format**: EDF+ per subject/run (plus a matching `.event` file). 

## Fixed Parameters
- **Sampling rate (Fs)**: **160 Hz**  
- **Window length (W)**: **160 samples** (1.0 s)  
- **Hop (H)**: **80 samples** (0.5 s)  
- **Channels (C)**: **64**

## Channel Order
- **Source of truth**: EDF header **signal order 0–63** for each file. We snapshot channel names from the first used record and reuse that order for all processing.  
- **Montage reference**: Official 64-electrode 10–10 montage figure provided with the dataset (numbers under each label show the order 1–64; EDF signals are 0–63).
 *note: I found the figure relevant to this but then i lost it!! i cant find it idk where it went. maybe im hallucinating*
- **Saved snapshot**: `docs/channel_order.json` (array of 64 channel names in EDF order). (*note: i still have to add this*)

## Units
- **EEG potentials**, physical units recorded in the EDF header (typically **µV**). Our code converts to **Volts** internally if a library expects V, but all reporting uses **µV**. (*note: ok this part, i got from chatgpt. so im not sure if it is correct. like the 'our code converts to volts' part...*)

## Reference Scheme
- **As recorded in EDF** (dataset page does not impose a single fixed reference). Our pipeline applies **common average reference (CAR)** as the first step to ensure consistency across runs.

## Annotations / Labels (kept for optional analyses)
- EDF annotation channel (and `.event` file) encodes **T0/T1/T2**:
  - **T0**: rest  
  - **T1**: onset of left fist (runs 3/4/7/8/11/12) or both fists (runs 5/6/9/10/13/14)  
  - **T2**: onset of right fist (3/4/7/8/11/12) or both feet (5/6/9/10/13/14)  
  We don’t require labels for our baseline kernels, but we keep them for sanity 

## Preprocessing (before any kernels)
- **None** beyond decoding EDF (no filtering, no artifact rejection, no resampling; Fs already 160 Hz). Any re-referencing is documented above (CAR at start of pipeline).
- *NOTE: from what I can tell, this dataset is completely raw, and hasn't been cleaned whatsoever. but i have to go through and more thoroughly read the research paper to be sure.*
