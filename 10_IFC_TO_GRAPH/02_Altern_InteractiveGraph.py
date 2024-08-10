import ifcopenshell
import re
import networkx as nx
import pandas as pd
import csv
import pickle
import os
from pyvis.network import Network

# Funktion zum Laden der IFC-Datei
def load_ifc_file(file_path):
    return ifcopenshell.open(file_path)

# Funktion zum Filtern von IfcSpaces nach Geschossname
def filter_ifcspaces_by_storey(spaces, storey_name):
    filtered_spaces = []
    for space in spaces:
        for rel in space.Decomposes:
            if rel.is_a("IfcRelAggregates") and rel.RelatingObject.is_a("IfcBuildingStorey"):
                if rel.RelatingObject.Name == storey_name:
                    filtered_spaces.append(space)
                    break
    return filtered_spaces

# Funktion zum Filtern von IfcSpaces nach Namen mit Ziffern (1-5 Ziffern)
def filter_spaces_by_name(spaces):
    digit_pattern = re.compile(r'^\d{1,5}$')
    filtered_spaces = []
    for space in spaces:
        if digit_pattern.match(space.Name):
            filtered_spaces.append(space)
    return filtered_spaces

# Funktion zum Laden und Verarbeiten einer CSV-Datei für Rauminformationen
def process_csv_room_connections(G, csv_file, access_type):
    edges = []
    with open(csv_file, 'r') as file:
        for line in file:
            parts = line.strip().split(';')
            main_room_global_id = parts[0]
            if len(parts) > 1:
                connected_rooms_global_ids = parts[1].split(',')
                for neighbor_global_id in connected_rooms_global_ids:
                    edges.append((main_room_global_id, neighbor_global_id))
    
    for edge in edges:
        room1 = None
        room2 = None
        for node in G.nodes:
            if G.nodes[node]["GlobalId"] == edge[0]:
                room1 = node
            if G.nodes[node]["GlobalId"] == edge[1]:
                room2 = node
        if room1 and room2:
            G.add_edge(room1, room2, Access=access_type)

# Funktion zum Hinzufügen von Türen und Fenstern als Knoten und Kanten
def process_doors_and_windows(G, ifc_file, csv_file, element_type, color, category):
    edges = []
    elements = set()
    with open(csv_file, 'r') as file:
        for line in file:
            parts = line.strip().split(';')
            element_global_id = parts[0]
            connected_rooms_global_ids = parts[1].split(',') if len(parts) > 1 else []
            
            element = next((e for e in ifc_file.by_type(element_type) if e.GlobalId == element_global_id), None)
            
            if element:
                element_oid = element.id()
                elements.add((f"{element_type.split('Ifc')[-1]}_{element_oid}", element_global_id, element_oid))
            
                for room_global_id in connected_rooms_global_ids:
                    edges.append((element_oid, room_global_id))
    
    for element_name, element_global_id, element_oid in elements:
        G.add_node(element_name, color=color, GlobalId=element_global_id, OID=element_oid)
    
    for edge in edges:
        element = f"{element_type.split('Ifc')[-1]}_{edge[0]}"
        room = None
        for node in G.nodes:
            if G.nodes[node]["GlobalId"] == edge[1]:
                room = node
                break
        if room:
            G.add_edge(element, room, Category=category)

# Funktion zum Filtern von IfcWalls nach Geschossname und Hinzufügen als Knoten
def process_walls(G, ifc_file, storey_name):
    def get_storey(element):
        for rel in element.ContainedInStructure:
            if rel.is_a("IfcRelContainedInSpatialStructure") and rel.RelatingStructure.is_a("IfcBuildingStorey"):
                return rel.RelatingStructure
        return None

    all_walls = ifc_file.by_type("IfcWall")
    walls_in_storey = []
    for wall in all_walls:
        storey = get_storey(wall)
        if storey and storey.Name == storey_name:
            walls_in_storey.append((wall.id(), wall.GlobalId))
    
    for wall_oid, wall_global_id in walls_in_storey:
        node_label = f"Wall_{wall_oid}"
        G.add_node(node_label, color='grey', GlobalId=wall_global_id, OID=wall_oid)

# Funktion zum Verarbeiten der CSV-Dateien für Wände und Räume
def process_walls_and_rooms(G, csv_file, all_walls, relation):
    def get_wall_oid_by_guid(walls, guid):
        for wall in walls:
            if wall.GlobalId == guid:
                return wall.id()
        return None
    
    with open(csv_file, 'r') as file:
        reader = csv.reader(file, delimiter=';')
        for row in reader:
            space_global_id = row[0]
            wall_guids = row[1].split(',')
            space_node = None
            for node in G.nodes:
                if G.nodes[node].get("GlobalId") == space_global_id:
                    space_node = node
                    break
            if space_node:
                for wall_guid in wall_guids:
                    wall_oid = get_wall_oid_by_guid(all_walls, wall_guid)
                    if wall_oid is not None:
                        wall_node = f"Wall_{wall_oid}"
                        if wall_node in G:
                            G.add_edge(space_node, wall_node, Category=relation)

# Funktion zum Verarbeiten der CSV-Datei für benachbarte Wände
def process_wall_adjacency(G, csv_file, all_walls):
    def get_wall_oid_by_guid(walls, guid):
        for wall in walls:
            if wall.GlobalId == guid:
                return wall.id()
        return None
    
    with open(csv_file, 'r') as file:
        reader = csv.reader(file, delimiter=';')
        for row in reader:
            primary_wall_guid = row[0]
            connected_wall_guids = row[1].split(',')
            primary_wall_oid = get_wall_oid_by_guid(all_walls, primary_wall_guid)
            if primary_wall_oid is not None:
                primary_wall_node = f"Wall_{primary_wall_oid}"
                for connected_wall_guid in connected_wall_guids:
                    connected_wall_oid = get_wall_oid_by_guid(all_walls, connected_wall_guid)
                    if connected_wall_oid is not None:
                        connected_wall_node = f"Wall_{connected_wall_oid}"
                        if primary_wall_node in G and connected_wall_node in G:
                            G.add_edge(primary_wall_node, connected_wall_node, Category="IsConnected")

# Hauptfunktion zum Erstellen des Graphen
def main():
    # Pfade zu den Dateien
    ifc_file_path = "Hus28_test.ifc"
    csv_room_to_room = "Output01_RoomToRoom_BySeparationLine.csv"
    csv_doors = "Output02_RoomToRoom_ByDoors.csv"
    csv_windows = "Output03_RoomToRoom_ByWindows.csv"
    csv_walls = "Output04_RoomBoundingWalls.csv"
    csv_wall_adjacency = "Output06_Wall_Adjacancy.csv"
    csv_host_elements = "Output05_Hosts_of_WindowsAndDoors.csv"

    # IFC-Datei laden
    ifc_file = load_ifc_file(ifc_file_path)

    # Geschossname definieren
    storey_name = "Plan 10"

    # Graph erstellen
    G = nx.Graph()

    # IfcSpaces laden und filtern
    all_spaces = ifc_file.by_type("IfcSpace")
    spaces = filter_ifcspaces_by_storey(all_spaces, storey_name)
    spaces = filter_spaces_by_name(spaces)

    # Räume als Knoten hinzufügen
    for space in spaces:
        node_label = f"Room_{space.Name}"
        global_id = space.GlobalId
        G.add_node(node_label, color='yellow', GlobalId=global_id)

    # Raumverbindungen verarbeiten
    process_csv_room_connections(G, csv_room_to_room, "Direct")

    # Türen als Knoten und Kanten hinzufügen
    process_doors_and_windows(G, ifc_file, csv_doors, "IfcDoor", 'blue', "ContainedIn")

    # Fenster als Knoten und Kanten hinzufügen
    process_doors_and_windows(G, ifc_file, csv_windows, "IfcWindow", 'purple', "ContainedIn")

    # Wände verarbeiten und als Knoten hinzufügen
    process_walls(G, ifc_file, storey_name)

    # Wände und Räume verbinden
    process_walls_and_rooms(G, csv_walls, ifc_file.by_type("IfcWall"), "ContainedIn")

    # Wand-Adjazenz verarbeiten
    process_wall_adjacency(G, csv_wall_adjacency, ifc_file.by_type("IfcWall"))

    # Elemente in Wände einfügen
    process_walls_and_rooms(G, csv_host_elements, ifc_file.by_type("IfcWall"), "HostedBy")

    # Pyvis Network erstellen und visualisieren
    net = Network(notebook=False, height="1200px", width="1600px", select_menu=True, filter_menu=True)
    net.from_nx(G)

    # Farben der Knoten setzen
    for node in net.nodes:
        node['color'] = G.nodes[node['id']]['color']
        node['title'] = f"GlobalId: {G.nodes[node['id']]['GlobalId']}"

    # Farben der Kanten setzen und zusätzliche Informationen hinzufügen
    for edge in net.edges:
        edge_data = G.edges[(edge['from'], edge['to'])]
        edge['color'] = ('blue' if edge_data.get('Access') == 'Direct' else
                        'orange' if edge_data.get('Access') == 'Door' else
                        'purple' if edge_data.get('Access') == 'Window' else
                        'grey' if edge_data.get('Category') == 'ContainedIn' else
                        'red' if edge_data.get('Category') == 'IsConnected' else
                        'green' if edge_data.get('Category') == 'HostedBy' else
                        'black')
        edge['title'] = f"Category: {edge_data.get('Category', 'N/A')}<br>Access: {edge_data.get('Access', 'N/A')}"

    # HTML-Datei erstellen und anzeigen
    net.write_html("interactive_graph.html")

# Skript ausführen
if __name__ == "__main__":
    main()
