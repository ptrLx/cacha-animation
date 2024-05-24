import numpy as np
import pandas as pd
from scipy.interpolate import PchipInterpolator
#import matplotlib.pyplot as plt
import os
import json
from pathlib import Path

def main(time_step_ms, inactive_after_ms):
    for game_name in os.listdir("data/"):
        teams = dict()
        for team_json in os.listdir(f"data/{game_name}/log-by-user/"):
            team_name = team_json.rstrip(".json")
            team_dataframe = json_to_dataframe(f"data/{game_name}/log-by-user/{team_json}")
            teams[team_name] = team_dataframe
        interpol_dataframe = consolidate_data(teams, time_step_ms)
        Path(f"data/{game_name}/log-interpol").mkdir(parents=True, exist_ok=True)
        interpol_dataframe.to_parquet(f"data/{game_name}/log-interpol/interpol.parquet")
        connection_dataframe = connection_status(interpol_dataframe.index, teams, inactive_after_ms)
        connection_dataframe.to_parquet(f"data/{game_name}/log-interpol/connection.parquet")

def json_to_dataframe(path):
    with open(path) as file:
        data = json.load(file)
    data.sort(key=lambda entry: entry["current_location"]["timestamp"])
    lat = []
    lon = []
    timestamp = []
    for entry in data:
        c = entry["current_location"]
        lat.append(c["lat"])
        lon.append(c["lon"])
        timestamp.append(c["timestamp"])
    coords = np.array([lat, lon]).T
    team_dataframe = pd.DataFrame(coords, index=timestamp, columns=["lat", "lon"])
    return team_dataframe

def consolidate_data(teams, time_step_ms):
    min_times = [np.min(team_dataframe.index) for team_dataframe in teams.values()]
    max_times = [np.max(team_dataframe.index) for team_dataframe in teams.values()]
    #print("min times", np.array(sorted(min_times)) - min(min_times))
    #print("max times", max(max_times) - np.array(sorted(max_times)))
    min_time = max(min_times)
    max_time = min(max_times)
    # We lose a lot of precision for large timestamps, so shift the region
    # of interest to lie near zero
    time_equi = np.arange(0, max_time - min_time, time_step_ms)
    columns = pd.MultiIndex.from_product([teams.keys(), ["lat", "lon"]], names=["team_name", "dim"])
    interpol_dataframe = pd.DataFrame(index=time_equi+min_time, columns=columns)
    for team_name, team_dataframe in teams.items():
        spline_lat = PchipInterpolator(team_dataframe.index - min_time, team_dataframe["lat"])
        spline_lon = PchipInterpolator(team_dataframe.index - min_time, team_dataframe["lon"])
        interpol_dataframe[team_name, "lat"] = spline_lat(time_equi)
        interpol_dataframe[team_name, "lon"] = spline_lon(time_equi)
    return interpol_dataframe

def connection_status(time_equi, teams, inactive_after_ms):
    # assume time contains equidistant points
    time_step = time_equi[1] - time_equi[0]
    num_points = inactive_after_ms // time_step
    connection_dataframe = pd.DataFrame(index=time_equi, columns=teams.keys())
    for team_name, team_dataframe in teams.items():
        time_raw = team_dataframe.index
        active_connection = np.full(len(time_equi), True)
        current_raw_index = 0
        for i, t in enumerate(time_equi):
            while current_raw_index+1 < len(time_raw) and time_raw[current_raw_index+1] < t:
                current_raw_index += 1
            assert time_raw[current_raw_index] <= t
            if t - time_raw[current_raw_index] > inactive_after_ms:
                active_connection[i] = False
        #plt.plot(time_equi, active_connection)
        #plt.show()
        connection_dataframe[team_name] = active_connection
    return connection_dataframe

if __name__ == "__main__":
    main(time_step_ms=1000, inactive_after_ms=30_000)