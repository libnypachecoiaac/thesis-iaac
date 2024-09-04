import ifcopenshell
import csv
import math
from topologicpy.Topology import Topology
from topologicpy.Vertex import Vertex
from topologicpy.Face import Face
from topologicpy.Cell import Cell
from topologicpy.Cluster import Cluster
from topologicpy.Dictionary import Dictionary

# --- Functions for ifcspaces_to_topology ---
def get_translation_vector(placement):
    if placement and placement.Location:
        location = placement.Location
        return location.Coordinates[0], location.Coordinates[1], location.Coordinates[2]
    return 0.0, 0.0, 0.0

def get_direction_vector(ifc_file, direction):
    if direction:
        dir_ref = ifc_file[direction.id()]
        if dir_ref:
            return tuple(dir_ref.DirectionRatios)
    return (0.0, 0.0, 1.0)

def get_axis_vector(placement):
    if placement and placement.Axis:
        return tuple(placement.Axis.DirectionRatios)
    return (0.0, 0.0, 1.0)

def rotate_point(x, y, angle):
    radians = math.radians(angle)
    cos_angle = math.cos(radians)
    sin_angle = math.sin(radians)
    new_x = x * cos_angle - y * sin_angle
    new_y = x * sin_angle + y * cos_angle
    return new_x, new_y

def rotate_point_around_x(x, y, z, angle):
    radians = math.radians(angle)
    cos_angle = math.cos(radians)
    sin_angle = math.sin(radians)
    new_y = y * cos_angle - z * sin_angle
    new_z = y * sin_angle + z * cos_angle
    return x, new_y, new_z

def apply_transformation(coordinates, translation_vector, axis_vector, ref_direction_vector):
    transformed_coordinates = []

    for point in coordinates:
        x, y = point
        z = 0.0

        if axis_vector == (0.0, 0.0, -1.0):
            x, y, z = rotate_point_around_x(x, y, z, 180)
        if ref_direction_vector == (0.0, 1.0, 0.0):
            x, y = rotate_point(x, y, 90)
        elif ref_direction_vector == (-1.0, 0.0, 0.0):
            x, y = rotate_point(x, y, 180)
        elif ref_direction_vector == (0.0, -1.0, 0.0):
            x, y = rotate_point(x, y, 270)
        
        new_x = x + translation_vector[0]
        new_y = y + translation_vector[1]
        new_z = z + translation_vector[2]
        transformed_coordinates.append((new_x, new_y, new_z))

    return transformed_coordinates

def extract_face_from_space(space, ifc_file):
    representation = space.Representation
    if representation:
        shape = representation.Representations[0]
        if shape and shape.Items:
            for item in shape.Items:
                if item.is_a("IfcExtrudedAreaSolid"):
                    profile = item.SweptArea
                    if profile and profile.is_a("IfcArbitraryClosedProfileDef"):
                        curve = profile.OuterCurve
                        if curve and curve.is_a("IfcIndexedPolyCurve"):
                            point_list = curve.Points
                            if point_list and point_list.is_a("IfcCartesianPointList2D"):
                                coordinates = point_list.CoordList
                                translation_vector = get_translation_vector(item.Position)
                                axis_vector = get_axis_vector(item.Position)
                                ref_direction_vector = get_direction_vector(ifc_file, item.Position.RefDirection)
                                if coordinates:
                                    transformed_coordinates = apply_transformation(coordinates, translation_vector, axis_vector, ref_direction_vector)
                                    vertices = [Vertex.ByCoordinates(x, y, z) for x, y, z in transformed_coordinates]
                                    face = Face.ByVertices(vertices)
                                    return face
    return None

def ifcspaces_to_topology(ifc_file, spaces_in_storey):
    faces_and_names = []
    for index, space in enumerate(spaces_in_storey, start=1):
        print(f"Generating Face {index}/{len(spaces_in_storey)}")
        face = extract_face_from_space(space, ifc_file)
        if face:
            faces_and_names.append((face, space.GlobalId))
        else:
            print(f"Could not generate face for space {index}.")

    cells = []
    for face, name in faces_and_names:
        cell = Cell.ByThickenedFace(face, thickness=1500, bothSides=True)
        cell_dict = Dictionary.ByKeyValue("Name", name)
        cell.SetDictionary(cell_dict)
        cells.append(cell)

    building = Cluster.ByTopologies(cells)
    building = Topology.SelfMerge(building)

    return building

# --- Functions for topology_spaces_to_csv ---
def get_cell_OID(cell):
    dictionary = Topology.Dictionary(cell)
    if dictionary:
        name = Dictionary.ValueAtKey(dictionary, "Name")
        return name if name else str(cell)
    return str(cell)

def topology_spaces_to_csv(building):
    cells = Topology.Cells(building)
    touching_cells = {}

    def cells_share_face(cell1, cell2):
        shared_faces = Topology.SharedFaces(cell1, cell2)
        return len(shared_faces) > 0

    for i, cell1 in enumerate(cells):
        touching = []
        for j, cell2 in enumerate(cells):
            if i != j and cells_share_face(cell1, cell2):
                touching.append(get_cell_OID(cell2))
        if touching:
            touching_cells[get_cell_OID(cell1)] = touching

    csv_data = []
    for cell_name, touch_cell_names in touching_cells.items():
        if cell_name not in touch_cell_names:
            touching_guids = ",".join(touch_cell_names)
            row = [cell_name, touching_guids]
            csv_data.append(row)

    with open('Output01_RoomToRoom_BySeparationLine.csv', mode='w', newline='') as file:
        writer = csv.writer(file, delimiter=';')
        for row in csv_data:
            writer.writerow(row)

    print("Data has been written to Output01_RoomToRoom_BySeparationLine.csv")

# --- Functions for doorinfo_to_csv ---
def doorinfo_to_csv(ifc_file, all_doors, target_storey):
    door_to_room = {}
    for rel in ifc_file.by_type("IfcRelSpaceBoundary"):
        if rel.RelatedBuildingElement in all_doors:
            door = rel.RelatedBuildingElement
            door_global_id = door.GlobalId
            
            door_storey = door.ContainedInStructure
            if door_storey and door_storey[0].RelatingStructure == target_storey:
                room = rel.RelatingSpace
                if room:
                    room_global_id = room.GlobalId
                    if door_global_id in door_to_room:
                        door_to_room[door_global_id].append(room_global_id)
                    else:
                        door_to_room[door_global_id] = [room_global_id]

    if door_to_room:
        with open('Output02_RoomToRoom_ByDoors.csv', 'w', newline='') as csvfile:
            csvwriter = csv.writer(csvfile, delimiter=';')
            for door_global_id, room_global_ids in door_to_room.items():
                room_guids_combined = ",".join(room_global_ids)
                csvwriter.writerow([door_global_id, room_guids_combined])
        print("Data has been written to Output02_RoomToRoom_ByDoors.csv")
    else:
        print("door_to_room is empty, no data to write to CSV.")

# --- Functions for windowinfo_to_csv ---
def get_storey(element):
    for rel in element.ContainedInStructure:
        if rel.is_a("IfcRelContainedInSpatialStructure") and rel.RelatingStructure.is_a("IfcBuildingStorey"):
            return rel.RelatingStructure
    return None

def windowinfo_to_csv(ifc_file, ifc_windows, target_storey):
    window_to_room = {}
    for rel in ifc_file.by_type("IfcRelSpaceBoundary"):
        if rel.RelatedBuildingElement in ifc_windows:
            window = rel.RelatedBuildingElement
            window_guid = window.GlobalId
            
            window_storey = get_storey(window)
            if window_storey == target_storey:
                room = rel.RelatingSpace
                if room:
                    room_guid = room.GlobalId
                    if window_guid not in window_to_room:
                        window_to_room[window_guid] = []
                    window_to_room[window_guid].append(room_guid)

    with open('Output03_RoomToRoom_ByWindows.csv', 'w', newline='') as csvfile:
        csvwriter = csv.writer(csvfile, delimiter=';')
        for window_guid, room_guids in window_to_room.items():
            row = [window_guid, ",".join(room_guids)]
            csvwriter.writerow(row)

    print("Results have been saved to Output03_RoomToRoom_ByWindows.csv")

# --- Functions for room_bounding_walls_to_csv ---
def room_bounding_walls_to_csv(ifc_file, target_storey, filtered_spaces):
    space_to_walls = []

    for space in filtered_spaces:
        space_guid = space.GlobalId
        walls = []
        for rel_space_boundary in ifc_file.by_type("IfcRelSpaceBoundary"):
            if rel_space_boundary.RelatingSpace == space:
                if rel_space_boundary.RelatedBuildingElement and rel_space_boundary.RelatedBuildingElement.is_a("IfcWall"):
                    wall_guid = rel_space_boundary.RelatedBuildingElement.GlobalId
                    walls.append(wall_guid)

        space_to_walls.append({
            "space_guid": space_guid,
            "walls": walls
        })

        print(f"Space ({space_guid}) analysed - Found {len(walls)} Walls")

    with open('Output04_RoomBoundingWalls.csv', 'w', newline='') as csvfile:
        csvwriter = csv.writer(csvfile, delimiter=';')
        for entry in space_to_walls:
            csvwriter.writerow([
                entry["space_guid"],
                ",".join(entry["walls"])
            ])

    print("Data has been written to Output04_RoomBoundingWalls.csv")

# --- Functions for hosts_of_windows_and_doors ---
def hosts_of_windows_and_doors(ifc_file, target_storey):
    elements_to_walls = []

    def find_hosting_wall(opening_element):
        for rel_voids in ifc_file.by_type("IfcRelVoidsElement"):
            if rel_voids.RelatedOpeningElement == opening_element:
                return rel_voids.RelatingBuildingElement
        return None

    for rel_contained in target_storey.ContainsElements:
        for element in rel_contained.RelatedElements:
            if element.is_a("IfcDoor") or element.is_a("IfcWindow"):
                element_type = element.is_a()
                element_guid = element.GlobalId

                target_opening = None
                for rel_fills in ifc_file.by_type("IfcRelFillsElement"):
                    if rel_fills.RelatedBuildingElement == element:
                        target_opening = rel_fills.RelatingOpeningElement
                        break

                if target_opening:
                    hosting_wall = find_hosting_wall(target_opening)
                    if hosting_wall:
                        wall_guid = hosting_wall.GlobalId
                        elements_to_walls.append({
                            "element_type": element_type,
                            "element_guid": element_guid,
                            "wall_guid": wall_guid
                        })

    with open('Output05_Hosts_of_WindowsAndDoors.csv', 'w', newline='') as csvfile:
        csvwriter = csv.writer(csvfile, delimiter=';')
        for entry in elements_to_walls:
            csvwriter.writerow([entry["element_type"], entry["element_guid"], entry["wall_guid"]])

    print("Data has been written to Output05_Hosts_of_WindowsAndDoors.csv")

# --- Functions for wall_to_wall_connectivity ---
def find_touching_walls(topology1, topology2):
    cells1 = Topology.Cells(topology1)
    cells2 = Topology.Cells(topology2)

    for index1, cell1 in enumerate(cells1):
        for index2, cell2 in enumerate(cells2):
            
            # Check if cell1 and cell2 are valid Topology objects
            if not isinstance(cell1, Topology) or not isinstance(cell2, Topology):
                print(f"Invalid topology object: cell1={cell1}, cell2={cell2}")
                continue

            # Print the indices and GUIDs of the topologies being processed
            print(f"Processing Topology {index1} and {index2}")
            print(f"Cell1 GUID: {Dictionary.ValueAtKey(Topology.Dictionary(cell1), 'IFC_guid')}")
            print(f"Cell2 GUID: {Dictionary.ValueAtKey(Topology.Dictionary(cell2), 'IFC_guid')}")

            try:
                # Attempt to merge the cells
                merged_cell = Topology.Merge(cell1, cell2)
                shared_faces = Topology.SharedFaces(
                    Topology.Cells(merged_cell)[0], Topology.Cells(merged_cell)[1]
                )
                if shared_faces:
                    return True
            except RuntimeError as e:
                # Catch and print any RuntimeErrors from the merge operation
                print(f"Failed to merge topologies: {e}")
                print(f"Cell1: {cell1}, Cell2: {cell2}")
                continue

    return False

def wall_to_wall_connectivity(ifc_file, storey_name):
    print("Starting Check for Wall connectivity")

    topology = Topology.ByIFCFile(file=ifc_file, transferDictionaries=True, includeTypes=['IfcWall'])
    print("Initial topology created successfully.")

    wall_guids_in_storey = []
    for wall in ifc_file.by_type('IfcWall'):
        for rel in ifc_file.by_type("IfcRelContainedInSpatialStructure"):
            if wall in rel.RelatedElements:
                storey = rel.RelatingStructure
                if storey and storey.Name == storey_name:
                    wall_guids_in_storey.append(wall.GlobalId)
                break 

    topologies_in_storey = []

    for topo in topology:
        topo_dict = Topology.Dictionary(topo)
        topo_guid = Dictionary.ValueAtKey(topo_dict, "IFC_guid")
        if topo_guid in wall_guids_in_storey:
            topologies_in_storey.append(topo)

    touching_walls = []

    for i in range(len(topologies_in_storey)):
        print(f"Check of Wall {i} / {len(topologies_in_storey)}")
        for j in range(i + 1, len(topologies_in_storey)):
            if find_touching_walls(topologies_in_storey[i], topologies_in_storey[j]):
                touching_walls.append((i, j))

    def get_ifc_guid(topo):
        topo_dict = Topology.Dictionary(topo)
        return Dictionary.ValueAtKey(topo_dict, "IFC_guid")

    index_to_guid = {i: get_ifc_guid(topo) for i, topo in enumerate(topologies_in_storey)}

    touching_walls_dict = {index_to_guid[i]: [] for i in range(len(topologies_in_storey))}

    for i, j in touching_walls:
        touching_walls_dict[index_to_guid[i]].append(index_to_guid[j])
        touching_walls_dict[index_to_guid[j]].append(index_to_guid[i])

    output_file = 'Output06_Wall_Adjacancy.csv'

    with open(output_file, mode='w', newline='') as file:
        writer = csv.writer(file, delimiter=';')
        for key, value in touching_walls_dict.items():
            touching_guids = ",".join(value)
            row = [key, touching_guids]
            writer.writerow(row)

    print(f'Results written to {output_file}')
