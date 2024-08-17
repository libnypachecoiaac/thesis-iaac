import ifcopenshell
import re
import yaml
from neo4j import GraphDatabase
import csv

# Funktion, um IfcSpaces nach Geschossname zu filtern
def filter_ifcspaces_by_storey(spaces, storey_name):
    filtered_spaces = []
    for space in spaces:
        for rel in space.Decomposes:
            if rel.is_a("IfcRelAggregates") and rel.RelatingObject.is_a("IfcBuildingStorey"):
                if rel.RelatingObject.Name == storey_name:
                    filtered_spaces.append(space)
                    break
    return filtered_spaces

# Funktion, um IfcSpaces nach Namen mit Ziffern (1-5 Ziffern) zu filtern
def filter_spaces_by_name(spaces):
    digit_pattern = re.compile(r'^\d{1,5}$')
    filtered_spaces = []
    for space in spaces:
        if digit_pattern.match(space.Name):
            filtered_spaces.append(space)
    return filtered_spaces

# Funktion, um IfcSpaces als Knoten in Neo4j anzulegen und mit den spezifischen Daten anzureichern
def create_ifcspace_nodes(driver, spaces):
    with driver.session() as session:
        for space in spaces:
            # Zusätzliche Attribute aus der IFC-Datei extrahieren
            global_id = space.GlobalId
            long_name = decode_ifc_text(space.LongName) if space.LongName else 'N/A'
            
            # Mengenwerte aus der IFC-Datei extrahieren
            height, gross_floor_area, gross_volume = extract_quantities(space)
            
            # Knoten erstellen und mit spezifischen Daten anreichern
            session.write_transaction(
                add_space_node, global_id, space.id(), long_name, height, gross_floor_area, gross_volume
            )

def add_space_node(tx, global_id, oid, long_name, height, gross_floor_area, gross_volume):
    tx.run(
        """
        MERGE (n:Room {GlobalId: $global_id})
        ON CREATE SET n.OID = $oid
        SET n.Name = $long_name,
            n.Height = $height,
            n.GrossFloorArea = $gross_floor_area,
            n.GrossVolume = $gross_volume
        """,
        global_id=global_id,
        oid=oid,
        long_name=long_name,
        height=height,
        gross_floor_area=gross_floor_area,
        gross_volume=gross_volume
    )

# Funktion, um Mengenwerte (Height, GrossFloorArea, GrossVolume) aus der IFC-Datei zu extrahieren
def extract_quantities(element):
    height = None
    gross_floor_area = None
    gross_volume = None

    # Durchlaufe die Mengen der Elementdefinitionen
    if element:
        for definition in element.IsDefinedBy:
            if hasattr(definition.RelatingPropertyDefinition, "Quantities"):
                quantities = definition.RelatingPropertyDefinition.Quantities
                
                for quantity in quantities:
                    if quantity.Name == "Height":
                        height = quantity.LengthValue
                    elif quantity.Name == "GrossFloorArea":
                        gross_floor_area = quantity.AreaValue
                    elif quantity.Name == "GrossVolume":
                        gross_volume = quantity.VolumeValue
    
    return height, gross_floor_area, gross_volume

# Funktion, um Türen und Fenster als Knoten in Neo4j anzulegen und mit den entsprechenden Räumen zu verbinden
def process_doors_and_windows(driver, ifc_file, csv_file, element_type, element_label):
    with driver.session() as session:
        with open(csv_file, 'r') as file:
            for line in file:
                parts = line.strip().split(';')
                element_global_id = parts[0]
                connected_rooms_global_ids = parts[1].split(',') if len(parts) > 1 else []

                element = next((e for e in ifc_file.by_type(element_type) if e.GlobalId == element_global_id), None)
                
                if element:
                    element_oid = element.id()
                    construction_type = extract_property_value(element, 'Construction Type', 'text')
                    height = extract_property_value(element, 'Height', 'number')
                    width = extract_property_value(element, 'Width', 'number')
                    area = extract_property_value(element, 'Area', 'area')
                    if element_label == "Window":
                        sill_height = extract_property_value(element, 'Sill Height', 'number')
                        material_interior = extract_property_value(element, 'Material Interior', 'text')
                        material_exterior = extract_property_value(element, 'Material Exterior', 'text')
                        type_name = extract_property_value(element, 'Family and Type', 'text')
                    else:
                        external = extract_property_value(element, 'IsExternal', 'bool')
                        object_type = extract_property_value(element, 'Family and Type', 'text')

                    session.write_transaction(
                        add_element_node, element_label, element_global_id, element_oid, 
                        construction_type, height, width, area, 
                        sill_height if element_label == "Window" else None,
                        material_interior if element_label == "Window" else None,
                        material_exterior if element_label == "Window" else None,
                        type_name if element_label == "Window" else object_type,
                        external if element_label == "Door" else None
                    )

                    # Verbindungen zu den Räumen herstellen
                    for room_global_id in connected_rooms_global_ids:
                        session.write_transaction(
                            add_edge, element_global_id, room_global_id, "ContainedIn"
                        )

def add_element_node(tx, element_label, global_id, oid, construction_type, height, width, area, sill_height, material_interior, material_exterior, type_name, external):
    if element_label == "Window":
        tx.run(
            """
            MERGE (n:Window {GlobalId: $global_id})
            ON CREATE SET n.Object = 'Window', n.OID = $oid
            SET n.ConstructionType = $construction_type,
                n.Height = $height,
                n.Width = $width,
                n.Area = $area,
                n.SillHeight = $sill_height,
                n.MaterialInterior = $material_interior,
                n.MaterialExterior = $material_exterior,
                n.Type = $type_name,
                n.name = $type_name
            """,
            global_id=global_id,
            oid=oid,
            construction_type=construction_type,
            height=height,
            width=width,
            area=area,
            sill_height=sill_height,
            material_interior=material_interior,
            material_exterior=material_exterior,
            type_name=type_name
        )
    elif element_label == "Door":
        tx.run(
            """
            MERGE (n:Door {GlobalId: $global_id})
            ON CREATE SET n.Object = 'Door', n.OID = $oid
            SET n.ConstructionType = $construction_type,
                n.Height = $height,
                n.Width = $width,
                n.Area = $area,
                n.ObjectType = $type_name,
                n.External = $external,
                n.name = $type_name
            """,
            global_id=global_id,
            oid=oid,
            construction_type=construction_type,
            height=height,
            width=width,
            area=area,
            type_name=type_name,
            external=external
        )

# Funktion, um eine Verbindung zwischen zwei Knoten in Neo4j anzulegen (ohne Duplikate)
def add_edge(tx, room1_global_id, room2_global_id, category):
    # Sortiere die IDs, um eine konsistente Reihenfolge zu gewährleisten
    sorted_ids = sorted([room1_global_id, room2_global_id])

    # Wähle das passende Label für die Beziehung
    label = "Access" if category in ["Direct", "Door", "Window"] else category
    access_type = category if category in ["Direct", "Door", "Window"] else None

    if access_type:
        tx.run(
            f"""
            MATCH (a {{GlobalId: $room1_global_id}}), (b {{GlobalId: $room2_global_id}})
            MERGE (a)-[r:{label}]->(b)
            ON CREATE SET r.AccessType = $access_type
            """,
            room1_global_id=sorted_ids[0],
            room2_global_id=sorted_ids[1],
            access_type=access_type
        )
    else:
        tx.run(
            f"""
            MATCH (a {{GlobalId: $room1_global_id}}), (b {{GlobalId: $room2_global_id}})
            MERGE (a)-[r:{label}]->(b)
            """,
            room1_global_id=sorted_ids[0],
            room2_global_id=sorted_ids[1]
        )

# Funktion, um Wände als Knoten in Neo4j anzulegen und sie mit Räumen zu verbinden
def process_walls(driver, ifc_file, storey_name):
    with driver.session() as session:
        walls = ifc_file.by_type("IfcWall")
        for wall in walls:
            wall_oid = wall.id()
            wall_global_id = wall.GlobalId
            storey = next((rel.RelatingStructure for rel in wall.ContainedInStructure if rel.is_a("IfcRelContainedInSpatialStructure")), None)
            if storey and storey.Name == storey_name:
                object_type = extract_property_value(wall, 'Type', 'text')
                load_bearing = extract_property_value(wall, 'LoadBearing', 'bool')
                is_external = extract_property_value(wall, 'IsExternal', 'bool')
                width = extract_property_value(wall, 'Width', 'number')
                height = extract_property_value(wall, 'Height', 'number')
                length = extract_property_value(wall, 'Length', 'number')
                area = extract_property_value(wall, 'GrossVolume', 'area')

                session.write_transaction(
                    add_wall_node, wall_global_id, wall_oid, storey_name, object_type, load_bearing, is_external, width, height, length, area
                )

def add_wall_node(tx, global_id, oid, storey_name, object_type, load_bearing, is_external, width, height, length, area):
    tx.run(
        """
        MERGE (n:Wall {GlobalId: $global_id})
        ON CREATE SET n.OID = $oid,
                      n.Storey = $storey_name,
                      n.Object = 'Wall',
                      n.ObjectType = $object_type,
                      n.LoadBearing = $load_bearing,
                      n.IsExternal = $is_external,
                      n.Width = $width,
                      n.Height = $height,
                      n.Length = $length,
                      n.Area = $area,
                      n.name = $object_type
        """,
        global_id=global_id,
        oid=oid,
        storey_name=storey_name,
        object_type=object_type,
        load_bearing=load_bearing,
        is_external=is_external,
        width=width,
        height=height,
        length=length,
        area=area
    )

# Funktion, um Wände mit Räumen zu verbinden
def process_walls_and_rooms(driver, csv_file, all_walls):
    with driver.session() as session:
        with open(csv_file, 'r') as file:
            reader = csv.reader(file, delimiter=';')
            for row in reader:
                space_global_id = row[0]
                wall_guids = row[1].split(',')
                for wall_guid in wall_guids:
                    wall_oid = next((wall.id() for wall in all_walls if wall.GlobalId == wall_guid), None)
                    if wall_oid:
                        session.write_transaction(
                            add_edge, wall_guid, space_global_id, "ContainedIn"
                        )

# Funktion, um benachbarte Wände zu verbinden
def process_wall_adjacency(driver, csv_file, all_walls):
    with driver.session() as session:
        with open(csv_file, 'r') as file:
            reader = csv.reader(file, delimiter=';')
            for row in reader:
                primary_wall_guid = row[0]
                connected_wall_guids = row[1].split(',')
                primary_wall_oid = next((wall.id() for wall in all_walls if wall.GlobalId == primary_wall_guid), None)
                if primary_wall_oid:
                    for connected_wall_guid in connected_wall_guids:
                        connected_wall_oid = next((wall.id() for wall in all_walls if wall.GlobalId == connected_wall_guid), None)
                        if connected_wall_oid:
                            session.write_transaction(
                                add_edge, primary_wall_guid, connected_wall_guid, "IsConnected"
                            )

# Funktion, um Fenster und Türen mit Wänden zu verbinden
def process_element_hosts(driver, ifc_file, csv_file, all_walls):
    with driver.session() as session:
        with open(csv_file, 'r') as file:
            reader = csv.reader(file, delimiter=';')
            for row in reader:
                element_type = row[0]  # e.g., "IfcDoor" or "IfcWindow"
                element_guid = row[1]  # GlobalId of the window or door
                wall_guid = row[2]     # GlobalId of the wall in which the element is hosted

                element_oid = next((e.id() for e in ifc_file.by_type(element_type) if e.GlobalId == element_guid), None)
                wall_oid = next((wall.id() for wall in all_walls if wall.GlobalId == wall_guid), None)
                if element_oid and wall_oid:
                    session.write_transaction(
                        add_edge, element_guid, wall_guid, "HostedBy"
                    )

# Funktion zum Dekodieren von Unicode-Sonderzeichen in IFC-TEXT
def decode_ifc_text(text):
    matches = re.findall(r'\\X\\([0-9A-Fa-f]{4})', text)
    for match in matches:
        text = text.replace(r'\X\{}'.format(match), chr(int(match, 16)))
    return text

# Funktion zum Extrahieren von Property-Werten aus IFC-Dateien
def extract_property_value(ifc_element, property_name, value_type):
    for rel in ifc_element.IsDefinedBy:
        if rel.is_a("IfcRelDefinesByProperties"):
            props = rel.RelatingPropertyDefinition
            if props.is_a("IfcPropertySet"):
                for prop in props.HasProperties:
                    if prop.Name == property_name:
                        if value_type == 'text' and hasattr(prop.NominalValue, 'wrappedValue'):
                            return decode_ifc_text(prop.NominalValue.wrappedValue)
                        elif value_type == 'number' and hasattr(prop.NominalValue, 'wrappedValue'):
                            return round(prop.NominalValue.wrappedValue)
                        elif value_type == 'area' and hasattr(prop.NominalValue, 'wrappedValue'):
                            return round(prop.NominalValue.wrappedValue, 3)
                        elif value_type == 'bool' and hasattr(prop.NominalValue, 'wrappedValue'):
                            return prop.NominalValue.wrappedValue
    return None

# Funktion, um direkte Verbindungen zwischen Räumen herzustellen
def process_direct_connections(driver, csv_file):
    with driver.session() as session:
        with open(csv_file, 'r') as file:
            for line in file:
                parts = line.strip().split(';')
                main_room_global_id = parts[0]
                if len(parts) > 1:
                    connected_rooms_global_ids = parts[1].split(',')
                    for neighbor_global_id in connected_rooms_global_ids:
                        if main_room_global_id != neighbor_global_id:
                            room_pair = sorted([main_room_global_id, neighbor_global_id])  # Sortieren der IDs
                            session.write_transaction(
                                add_edge, room_pair[0], room_pair[1], "Direct"
                            )

# Funktion, um Türen- und Fensterverbindungen zwischen Räumen herzustellen
def process_element_connections(driver, csv_file, access_type):
    with driver.session() as session:
        with open(csv_file, 'r') as file:
            for line in file:
                parts = line.strip().split(';')
                element_global_id = parts[0]
                if len(parts) > 1:
                    connected_rooms_global_ids = parts[1].split(',')
                    for i in range(len(connected_rooms_global_ids) - 1):
                        for j in range(i + 1, len(connected_rooms_global_ids)):
                            if connected_rooms_global_ids[i] != connected_rooms_global_ids[j]:
                                room_pair = sorted([connected_rooms_global_ids[i], connected_rooms_global_ids[j]])  # Sortieren der IDs
                                session.write_transaction(
                                    add_edge, room_pair[0], room_pair[1], access_type
                                )

# MAIN
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
