import ifcopenshell
import yaml
import re
from neo4j import GraphDatabase

from neo4j_functions import (
    create_ifcspace_nodes, 
    process_doors_and_windows, 
    process_walls, 
    process_walls_and_rooms, 
    process_wall_adjacency, 
    process_element_hosts, 
    process_direct_connections, 
    process_element_connections
)

def filter_ifcspaces_by_storey(spaces, storey_name):
    filtered_spaces = []
    for space in spaces:
        for rel in space.Decomposes:
            if rel.is_a("IfcRelAggregates") and rel.RelatingObject.is_a("IfcBuildingStorey"):
                if rel.RelatingObject.Name == storey_name:
                    filtered_spaces.append(space)
                    break
    return filtered_spaces

def filter_spaces_by_name(spaces):
    digit_pattern = re.compile(r'^\d{1,5}$')
    filtered_spaces = []
    for space in spaces:
        if digit_pattern.match(space.Name):
            filtered_spaces.append(space)
    return filtered_spaces

def main():
    # Paths
    csv_room_to_room = "Output01_RoomToRoom_BySeparationLine.csv"
    csv_doors = "Output02_RoomToRoom_ByDoors.csv"
    csv_windows = "Output03_RoomToRoom_ByWindows.csv"
    csv_walls = "Output04_RoomBoundingWalls.csv"
    csv_wall_adjacency = "Output06_Wall_Adjacancy.csv"
    csv_host_elements = "Output05_Hosts_of_WindowsAndDoors.csv"

    # Load config.yaml
    with open("config.yaml", "r") as f:
        config = yaml.safe_load(f)

    ifc_file_path = config["ifc_file"]
    storey_name = config["storey_name"]

    # Open IFC file
    ifc_file = ifcopenshell.open(ifc_file_path)
    print("IFC file opened successfully.")

    # Load and filter Rooms
    all_spaces = ifc_file.by_type("IfcSpace")
    spaces = filter_ifcspaces_by_storey(all_spaces, storey_name)
    spaces = filter_spaces_by_name(spaces)

    # Verbindung zu Neo4j herstellen
    uri = "bolt://localhost:7687"
    driver = GraphDatabase.driver(uri, auth=("neo4j", "iaacthesis"))

    # Knoten in Neo4j erstellen und mit Daten anreichern
    create_ifcspace_nodes(driver, spaces)

    # Türen und Fenster als Knoten hinzufügen und Verbindungen zu Räumen herstellen
    process_doors_and_windows(driver, ifc_file, csv_doors, "IfcDoor", "Door")
    process_doors_and_windows(driver, ifc_file, csv_windows, "IfcWindow", "Window")

    # Wände als Knoten hinzufügen
    process_walls(driver, ifc_file, storey_name)

    # Wände mit Räumen verbinden
    process_walls_and_rooms(driver, csv_walls, ifc_file.by_type("IfcWall"))

    # Wände untereinander verbinden
    process_wall_adjacency(driver, csv_wall_adjacency, ifc_file.by_type("IfcWall"))

    # Fenster und Türen mit Wänden verbinden
    process_element_hosts(driver, ifc_file, csv_host_elements, ifc_file.by_type("IfcWall"))

    # Verbindungen zwischen Räumen erstellen
    process_direct_connections(driver, csv_room_to_room)
    process_element_connections(driver, csv_doors, "Door")
    process_element_connections(driver, csv_windows, "Window")

    # Verbindung schließen
    driver.close()
    print("IfcSpaces, Türen, Fenster, Wände und Verbindungen wurden erfolgreich in Neo4j importiert.")

if __name__ == "__main__":
    main()
