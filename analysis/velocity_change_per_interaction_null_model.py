from slurmhelper import SLURMJob
import datetime

"""
This is a script for creating a dataframe of a null model for bee interactions and their post-interaction velocity 
change for the period 01.08.-25.08.2016 and 20.08-14.09.2019. The interaction null model is created by taking the 
distribution of the start and end times of a given interaction dataframe and selecting two random bees at those times 
that the bees were detected in the hive at that time. These pairs of bees are considered as "interacting" and their 
post-interaction speed change is calculated. For faster computation the job is divided that the time window of 4 minutes 
is one node in the slurmhelper job array.

Comment pipeline to create, run and concat results to a pandas DataFrame:
python velocity_change_per_interaction_null_model.py --create
python velocity_change_per_interaction_null_model.py --autorun
python velocity_change_per_interaction_concat.py
"""

VELOCITY_DF_PATH_2016 = "../data/2016/velocities_1_8-25_8_2016"
VELOCITY_DF_PATH_2019 = "../data/2019/velocities_20_8-14_9_2019"

INTERACTION_SIDE_1_DF_PATH_2016 = "../data/2016/interactions_side1.pkl"
INTERACTION_SIDE_2_DF_PATH_2016 = "../data/2016/interactions_side2.pkl"
INTERACTION_SIDE_1_DF_PATH_2019 = "../data/2019/interactions_side1.pkl"
INTERACTION_SIDE_2_DF_PATH_2019 = "../data/2019/interactions_side2.pkl"


def run_job_2019(
    dt_from=None,
    dt_to=None,
    interaction_model_path=None,
    velocities_path=None,
    cam_ids=None,
):
    # imports for run job
    import bb_behavior.db
    import bb_rhythm.interactions

    # subset interaction df by time window and get interaction count for sampling to retain count-time distribution
    df_grouped = bb_rhythm.interactions.get_sub_interaction_df_for_null_model_sampling(
        dt_from, dt_to, interaction_model_path
    )

    # server settings
    bb_behavior.db.base.server_address = "beequel.imp.fu-berlin.de:5432"
    bb_behavior.db.base.set_season_berlin_2019()
    bb_behavior.db.base.beesbook_season_config[
        "bb_detections"
    ] = "bb_detections_2019_berlin_orientationfix"

    # connect to DB
    with bb_behavior.db.base.get_database_connection(
        application_name="find_detections_in_frame"
    ) as db:

        # sample random bees from frame and assign them as interaction partners
        interactions = bb_rhythm.interactions.assign_random_bees_as_interactions(
            db, df_grouped, cam_ids=cam_ids
        )
        if not interactions:
            return {None: dict(error="No events found..")}

        # calculate per interaction post-interaction velocity changes
        bb_rhythm.interactions.add_post_interaction_velocity_change(
            interactions, velocity_df_path=velocities_path
        )
        return interactions


def run_job_2016(
    dt_from=None,
    dt_to=None,
    interaction_model_path=None,
    velocities_path=None,
    cam_ids=None,
):
    # imports for run job
    import datetime
    from sshtunnel import SSHTunnelForwarder
    import pandas as pd
    import numpy as np

    import bb_behavior.db
    import bb_rhythm.interactions

    # subset interaction df by time window and get interaction count for sampling to retain count-time distribution
    df_grouped = bb_rhythm.interactions.get_sub_interaction_df_for_null_model_sampling(
        dt_from, dt_to, interaction_model_path
    )

    # connect to ssh
    with SSHTunnelForwarder(
        "bommel.imp.fu-berlin.de",
        ssh_username="dbreader",
        ssh_password="dbreaderpw",
        remote_bind_address=("127.0.0.1", 5432),
    ) as server:

        # server settings
        bb_behavior.db.base.server_address = "localhost:{}".format(
            server.local_bind_port
        )
        bb_behavior.db.set_season_berlin_2016()
        bb_behavior.db.base.beesbook_season_config[
            "bb_alive_bees"
        ] = "alive_bees_2016_bayesian"

        # connect to DB
        with bb_behavior.db.base.get_database_connection(
            application_name="find_detections_in_frame"
        ) as db:
            cursor = db.cursor()

            # sample random bees from frame and assign them as interaction partners
            interactions = bb_rhythm.interactions.assign_random_bees_as_interactions(
                db, df_grouped, cam_ids=None
            )
            if not interactions:
                return {None: dict(error="No events found..")}

            # calculate per interaction post-interaction velocity changes
            bb_rhythm.interactions.add_post_interaction_velocity_change(
                interactions, velocity_df_path=velocities_path
            )
            return interactions


def generate_jobs_2019():
    import datetime
    import pytz

    # set time period and interaction time window
    dt_from = pytz.UTC.localize(datetime.datetime(2019, 8, 20))
    dt_to = pytz.UTC.localize(datetime.datetime(2019, 9, 14))
    delta = datetime.timedelta(minutes=4)

    # create jobs
    dt_current = dt_from - delta
    while dt_current <= dt_to:
        dt_current += delta
        yield dict(
            dt_from=dt_current,
            dt_to=dt_current + delta,
            interaction_model_path=INTERACTION_SIDE_1_DF_PATH_2019,
            velocities_path=VELOCITY_DF_PATH_2019,
            cam_ids=[0],
        )


def generate_jobs_2016():
    import datetime
    import pytz
    import os

    # set time period and interaction time window
    dt_from = pytz.UTC.localize(datetime.datetime(2016, 8, 1))
    dt_to = pytz.UTC.localize(datetime.datetime(2016, 8, 25))
    delta = datetime.timedelta(minutes=4)

    # create jobs
    dt_current = dt_from - delta
    while dt_current <= dt_to:
        dt_current += delta
        yield dict(
            dt_from=dt_current,
            dt_to=dt_current + delta,
            interaction_model_path=INTERACTION_SIDE_1_DF_PATH_2016,
            velocities_path=VELOCITY_DF_PATH_2016,
            cam_ids=[0, 1],
        )


# create job
job = SLURMJob("velocity_change_per_interaction_null_2019_side1", "/scratch/juliam98/")
job.map(run_job_2019, generate_jobs_2019())

# set job parameters
job.qos = "standard"
job.partition = "main,scavenger"
job.max_memory = "{}GB".format(50)
job.n_cpus = 1
job.max_job_array_size = 5000
job.time_limit = datetime.timedelta(minutes=60)
job.concurrent_job_limit = 50
job.custom_preamble = "#SBATCH --exclude=g[013-015]"

# run job
job()
