from neo4j import GraphDatabase
import csv
import re

def create_ifcspace_nodes(driver, spaces, storey_name):
    with driver.session() as session:
        for space in spaces:
            global_id = space.GlobalId
            long_name = decode_ifc_text(space.LongName) if space.LongName else 'N/A'
            height, gross_floor_area, gross_volume, net_floor_area = extract_quantities(space)
            
            # Level/Storey Name
            level = storey_name
            for rel in space.Decomposes:
                if rel.is_a("IfcRelAggregates") and rel.RelatingObject.is_a("IfcBuildingStorey"):
                    level = rel.RelatingObject.Name
                    break
            
            session.write_transaction(
                add_space_node, global_id, space.id(), long_name, height, gross_floor_area, gross_volume, net_floor_area, level
            )

def add_space_node(tx, global_id, oid, long_name, height, gross_floor_area, gross_volume, net_floor_area, level):
    tx.run(
        """
        MERGE (n:Room {GlobalId: $global_id})
        ON CREATE SET n.Object = 'Room', n.OID = $oid
        SET n.Name = $long_name,
            n.Height = $height,
            n.GrossFloorArea = $gross_floor_area,
            n.NetFloorArea = $net_floor_area,
            n.GrossVolume = $gross_volume,
            n.Level = $level
        """,
        global_id=global_id,
        oid=oid,
        long_name=long_name,
        height=height,
        gross_floor_area=gross_floor_area,
        net_floor_area=net_floor_area,
        gross_volume=gross_volume,
        level=level
    )

def process_doors_and_windows(driver, ifc_file, csv_file, element_type, element_label, storey_name):
    with driver.session() as session:
        with open(csv_file, 'r') as file:
            for line in file:
                parts = line.strip().split(';')
                element_global_id = parts[0]
                connected_rooms_global_ids = parts[1].split(',') if len(parts) > 1 else []

                element = next((e for e in ifc_file.by_type(element_type) if e.GlobalId == element_global_id), None)
                
                if element:
                    element_oid = element.id()
                    name = str(element.Name) if element.Name else None
                    height = extract_property_value(element, 'Height', 'number')
                    width = extract_property_value(element, 'Width', 'number')
                    area = extract_property_value(element, 'Area', 'area')
                    sill_height = extract_property_value(element, 'Sill Height', 'number') if element_label == "Window" else None
                    level = str(storey_name)  # Default level from storey_name

                    # Suche nach Level im Raum
                    for rel in element.ContainedInStructure:
                        if rel.is_a("IfcRelContainedInSpatialStructure") and rel.RelatingStructure.is_a("IfcBuildingStorey"):
                            level = str(rel.RelatingStructure.Name)  # Ensure level is a string
                            break
                    
                    # Zusätzliche Eigenschaften aus IfcWindowType oder IfcDoorType
                    material_panel = None
                    material_frame = None
                    operation_type = None
                    construction_type = None
                    is_external = None
                    type_mark = None
                    element_type_value = None

                    # Durchsuche die zugeordneten Typen für weitere Eigenschaften
                    for rel_def in ifc_file.by_type("IfcRelDefinesByType"):
                        if element in rel_def.RelatedObjects:
                            element_type_obj = rel_def.RelatingType

                            for prop_set in element_type_obj.HasPropertySets:
                                if prop_set.is_a("IfcPropertySet"):
                                    for prop in prop_set.HasProperties:
                                        if prop.is_a("IfcPropertySingleValue"):
                                            value = getattr(prop.NominalValue, 'wrappedValue', None)
                                            if prop.Name == "Material Panel":
                                                material_panel = str(value) if value else None
                                            elif prop.Name == "Material Frame":
                                                material_frame = str(value) if value else None
                                            elif prop.Name == "OperationType":
                                                operation_type = str(value) if value else None
                                            elif prop.Name == "Construction Type":
                                                construction_type = str(value) if value else None
                                            elif prop.Name == "Function":
                                                is_external = str(value).lower() == 'exterior' if value else None
                                            elif prop.Name == "Type Mark":
                                                type_mark = str(value) if value else None
                                            elif prop.Name == "Type":
                                                element_type_value = str(value) if value else None

                    # Überprüfung auf `Type` und andere Attribute in anderen Assoziationen
                    if not element_type_value or not is_external:
                        for rel_def in element.IsDefinedBy:
                            if rel_def.is_a("IfcRelDefinesByProperties"):
                                property_set = rel_def.RelatingPropertyDefinition
                                if property_set.is_a("IfcPropertySet"):
                                    for prop in property_set.HasProperties:
                                        if prop.is_a("IfcPropertySingleValue"):
                                            value = getattr(prop.NominalValue, 'wrappedValue', None)
                                            if prop.Name == "Function" and is_external is None:
                                                is_external = str(value).lower() == 'exterior' if value else None
                                            elif prop.Name == "Type" and not element_type_value:
                                                element_type_value = str(value) if value else None

                    session.write_transaction(
                        add_element_node, element_label, element_global_id, element_oid, name, height, width, area, sill_height, is_external, level, material_panel, material_frame, operation_type, construction_type, type_mark, element_type_value
                    )

                    for room_global_id in connected_rooms_global_ids:
                        session.write_transaction(
                            add_edge, element_global_id, room_global_id, "ContainedIn"
                        )

def add_element_node(tx, element_label, global_id, oid, name, height, width, area, sill_height, is_external, level, material_panel, material_frame, operation_type, construction_type, type_mark, element_type_value):
    if element_label == "Window":
        tx.run(
            """
            MERGE (n:Window {GlobalId: $global_id})
            ON CREATE SET n.OID = $oid,
                          n.Name = $name,
                          n.Height = $height,
                          n.Width = $width,
                          n.Area = $area,
                          n.SillHeight = $sill_height,
                          n.IsExternal = $is_external,
                          n.Level = $level,
                          n.MaterialPanel = $material_panel,
                          n.MaterialFrame = $material_frame,
                          n.OperationType = $operation_type,
                          n.ConstructionType = $construction_type,
                          n.TypeMark = $type_mark,
                          n.Type = $element_type_value
            """,
            global_id=global_id,
            oid=str(oid),  # Ensure oid is string
            name=name,
            height=height,
            width=width,
            area=area,
            sill_height=sill_height,
            is_external=is_external,
            level=level,
            material_panel=material_panel,
            material_frame=material_frame,
            operation_type=operation_type,
            construction_type=construction_type,
            type_mark=type_mark,
            element_type_value=element_type_value
        )
    elif element_label == "Door":
        tx.run(
            """
            MERGE (n:Door {GlobalId: $global_id})
            ON CREATE SET n.OID = $oid,
                          n.Name = $name,
                          n.Height = $height,
                          n.Width = $width,
                          n.Area = $area,
                          n.IsExternal = $is_external,
                          n.Level = $level,
                          n.MaterialPanel = $material_panel,
                          n.MaterialFrame = $material_frame,
                          n.OperationType = $operation_type,
                          n.ConstructionType = $construction_type,
                          n.TypeMark = $type_mark,
                          n.Type = $element_type_value
            """,
            global_id=global_id,
            oid=str(oid),  # Ensure oid is string
            name=name,
            height=height,
            width=width,
            area=area,
            is_external=is_external,
            level=level,
            material_panel=material_panel,
            material_frame=material_frame,
            operation_type=operation_type,
            construction_type=construction_type,
            type_mark=type_mark,
            element_type_value=element_type_value
        )

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

def process_walls(driver, ifc_file, storey_name):
    with driver.session() as session:
        walls = ifc_file.by_type("IfcWall")
        for wall in walls:
            wall_oid = wall.id()
            wall_global_id = wall.GlobalId
            storey = next((rel.RelatingStructure for rel in wall.ContainedInStructure if rel.is_a("IfcRelContainedInSpatialStructure")), None)
            if storey and storey.Name == storey_name:
                name = wall.Name
                load_bearing = extract_property_value(wall, 'LoadBearing', 'bool')
                is_external = extract_property_value(wall, 'IsExternal', 'bool')
                width = extract_property_value(wall, 'Width', 'number')
                height = extract_property_value(wall, 'Height', 'number')
                length = extract_property_value(wall, 'Length', 'number')

                session.write_transaction(
                    add_wall_node, wall_global_id, wall_oid, name, is_external, load_bearing, height, length, width
                )

def add_wall_node(tx, global_id, oid, name, is_external, load_bearing, height, length, width):
    tx.run(
        """
        MERGE (n:Wall {GlobalId: $global_id})
        ON CREATE SET n.OID = $oid,
                      n.Name = $name,
                      n.IsExternal = $is_external,
                      n.LoadBearing = $load_bearing,
                      n.Height = $height,
                      n.Length = $length,
                      n.Width = $width
        """,
        global_id=global_id,
        oid=oid,
        name=name,
        is_external=is_external,
        load_bearing=load_bearing,
        height=height,
        length=length,
        width=width
    )

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

def process_element_hosts(driver, ifc_file, csv_file, all_walls):
    with driver.session() as session:
        with open(csv_file, 'r') as file:
            reader = csv.reader(file, delimiter=';')
            for row in reader:
                element_type = row[0]
                element_guid = row[1]
                wall_guid = row[2]

                element_oid = next((e.id() for e in ifc_file.by_type(element_type) if e.GlobalId == element_guid), None)
                wall_oid = next((wall.id() for wall in all_walls if wall.GlobalId == wall_guid), None)
                if element_oid and wall_oid:
                    session.write_transaction(
                        add_edge, element_guid, wall_guid, "HostedBy"
                    )

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
                            room_pair = sorted([main_room_global_id, neighbor_global_id])  # Sort IDs
                            session.write_transaction(
                                add_edge, room_pair[0], room_pair[1], "Direct"
                            )

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
                                room_pair = sorted([connected_rooms_global_ids[i], connected_rooms_global_ids[j]])  # Sort IDs
                                session.write_transaction(
                                    add_edge, room_pair[0], room_pair[1], access_type
                                )

def add_edge(tx, room1_global_id, room2_global_id, category):
    sorted_ids = sorted([room1_global_id, room2_global_id])
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

# Funktion zum Dekodieren von Unicode-Sonderzeichen in IFC-TEXT
def decode_ifc_text(text):
    matches = re.findall(r'\\X\\([0-9A-Fa-f]{4})', text)
    for match in matches:
        text = text.replace(r'\X\{}'.format(match), chr(int(match, 16)))
    return text

# Funktion, um Mengenwerte (Height, GrossFloorArea, GrossVolume) aus IFC-Dateien zu extrahieren
def extract_quantities(element):
    height = None
    gross_floor_area = None
    gross_volume = None
    net_floor_area = None

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
                    elif quantity.Name == "NetFloorArea":
                        net_floor_area = quantity.AreaValue

    return height, gross_floor_area, gross_volume, net_floor_area

def process_furniture(driver, ifc_file, storey_name):
    # Definieren Sie die Schlüsselwörter für den Filter
    furniture_keywords = {
        "Bett": "ligg",
        "WC/Waschbecken/Dusche": "wc",
        "Waschmaschine": "trätt",
        "Kühlschrank": "kyl",
        "Gefrierschrank": "frys",
        "Herd": "spis"
    }

    with driver.session() as session:
        # Iteriere über alle `IfcRelContainedInSpatialStructure`-Beziehungen
        for rel in ifc_file.by_type("IfcRelContainedInSpatialStructure"):
            if rel.is_a("IfcRelContainedInSpatialStructure") and rel.RelatingStructure.is_a("IfcSpace"):
                space = rel.RelatingStructure
                space_global_id = space.GlobalId

                for furniture in rel.RelatedElements:
                    object_type = getattr(furniture, 'ObjectType', '').lower()  # `ObjectType` in Kleinbuchstaben
                    # Überprüfen, ob der `ObjectType` eines der Schlüsselwörter enthält
                    if any(keyword in object_type for keyword in furniture_keywords.values()):
                        furniture_global_id = furniture.GlobalId
                        level = storey_name  # Standardmäßig das Stockwerk aus `storey_name`

                        # Suchen nach Level im Raum
                        for structure_rel in furniture.ContainedInStructure:
                            if structure_rel.is_a("IfcRelContainedInSpatialStructure") and structure_rel.RelatingStructure.is_a("IfcBuildingStorey"):
                                level = str(structure_rel.RelatingStructure.Name)  # Sicherstellen, dass Level ein String ist
                                break

                        # Node für Möbelstück erstellen
                        session.write_transaction(
                            add_furniture_node, furniture_global_id, object_type, level
                        )

                        # Edge zwischen Möbelstück und Raum erstellen
                        session.write_transaction(
                            add_edge, furniture_global_id, space_global_id, "ContainedIn"
                        )
                    # Wenn `ObjectType` nicht passt, wird der Node nicht erstellt.

def add_furniture_node(tx, global_id, object_type, level):
    tx.run(
        """
        MERGE (n:Furniture {GlobalId: $global_id})
        ON CREATE SET n.ObjectType = $object_type,
                      n.Level = $level
        """,
        global_id=global_id,
        object_type=object_type,
        level=level
    )

def cleanup_isolated_nodes(driver, level_name):
    with driver.session() as session:
        # Löschen von isolierten Wall-Nodes auf dem spezifischen Geschoss
        session.run(
            """
            MATCH (w:Wall)
            WHERE NOT (w)--() AND w.Level = $level_name
            DELETE w
            """,
            level_name=level_name
        )

        # Löschen von isolierten Furniture-Nodes auf dem spezifischen Geschoss
        session.run(
            """
            MATCH (f:Furniture)
            WHERE NOT (f)--() AND f.Level = $level_name
            DELETE f
            """,
            level_name=level_name
        )
