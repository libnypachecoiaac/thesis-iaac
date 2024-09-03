import ifcopenshell
import ifcopenshell.geom
import numpy as np
import logging
import yaml
from topologicpy.Topology import Topology
from topologicpy.Vertex import Vertex
from topologicpy.Face import Face
from topologicpy.Cell import Cell
from topologicpy.Dictionary import Dictionary
from topologicpy.Cluster import Cluster
from topologicpy.CellComplex import CellComplex


# Setup logging
logging.basicConfig(filename='debug.log', level=logging.DEBUG, format='%(asctime)s %(levelname)s: %(message)s')

# Load config.yaml
with open("config.yaml", "r") as f:
    config = yaml.safe_load(f)

ifc_file_path = config["ifc_file"]
storey_name = config["storey_name"]

# Load IFC
ifc_file = ifcopenshell.open(ifc_file_path)

wall_guids = []

# Iterate all IfcWalls
for wall in ifc_file.by_type("IfcWall"):
    if wall.ContainedInStructure:
        for rel in wall.ContainedInStructure:
            # Check if Wall is in TargetStorey
            if rel.RelatingStructure.Name == "Plan 10":
                wall_guids.append(wall.GlobalId)

logging.debug("GUIDs von Wänden in Plan 10: %s", wall_guids)
logging.debug("Anzahl der Wände: %d", len(wall_guids))
print(f"Found {len(wall_guids)} Walls in specified Storey")

def create_rotation_matrix(axis, ref_direction):
    
    # Convert axis and reference direction to numpy arrays
    axis = np.array(axis)
    ref_dir = np.array(ref_direction)
    
    # Normalize the axis vector to ensure it has a unit length (necessary?)
    axis = axis / np.linalg.norm(axis)
    
    # Adjust ref_dir to be orthogonal to axis and normalize it
    ref_dir = ref_dir - np.dot(ref_dir, axis) * axis
    ref_dir = ref_dir / np.linalg.norm(ref_dir)
    
    # Calculate the local Y-axis as the cross product of the axis (Z-axis) and ref_dir (X-axis)
    local_y_axis = np.cross(axis, ref_dir)

    # Construct the rotation matrix using orthogonal vectors as columns
    rotation_matrix = np.array([
        ref_dir,         # local X-axis
        local_y_axis,    # local Y-axis
        axis             # local Z-axis
    ]).T  # Transpose to align vectors as columns

    return rotation_matrix

def rotation_matrix_to_axis_angle(R):

    # Calculate the angle of rotation
    angle = np.arccos((np.trace(R) - 1) / 2)
    angle_degrees = np.degrees(angle)

    # Calculate the rotation axis
    rx = R[2, 1] - R[1, 2]
    ry = R[0, 2] - R[2, 0]
    rz = R[1, 0] - R[0, 1]
    axis = np.array([rx, ry, rz])
    
    # Normalize the axis if it's not the zero vector
    if np.linalg.norm(axis) != 0:
        axis = axis / np.linalg.norm(axis)
    else:
        # Return a zero vector if axis calculation results in zero vector
        axis = np.array([0.0, 0.0, 0.0])

    return axis, angle_degrees

topo_walls = []
i = 1

for wall_guid in wall_guids:
    print(f"Reconstructing Wall {i}/{len(wall_guids)}")

    logging.debug("IFC GUID of Wall: %s", wall_guid)
    wall = ifc_file.by_guid(wall_guid)

    ### Gather Informations of Wall

    # Get local placement of the wall
    local_placement = wall.ObjectPlacement
    axis_placement = local_placement.RelativePlacement

    # Extract coordinates for wall's relative placement
    if isinstance(axis_placement.Location, ifcopenshell.entity_instance):
        wall_rel_placement = axis_placement.Location.Coordinates
    else:
        raise ValueError("No valid IFC Cartesian Point found in the wall's placement.")

    # Determine axis and reference direction, with defaults for Z and X axes if not specified
    wall_axis = axis_placement.Axis.DirectionRatios if axis_placement.Axis else (0.0, 0.0, 1.0)  # Default to Z-axis
    wall_ref_direction = axis_placement.RefDirection.DirectionRatios if axis_placement.RefDirection else (1.0, 0.0, 0.0)  # Default to X-axis

    logging.debug(f"Relative Placement of IfcWall: {wall_rel_placement}")
    logging.debug(f"Axis (Z-axis): {wall_axis}")
    logging.debug(f"RefDirection (X-axis): {wall_ref_direction}")

    ### Gather Informations of Layers

    # Retrieve the product definition shape of wall (which contains geometric representations)
    product_definition_shape = wall.Representation
    logging.debug("IFCPRODUCTDEFINITIONSHAPE found: %s", product_definition_shape)

    shape_aspects = []

    # Check if the product definition shape has any shape aspects
    if product_definition_shape and hasattr(product_definition_shape, 'HasShapeAspects'):
        shape_aspects = product_definition_shape.HasShapeAspects
        if shape_aspects:
            logging.debug(f"Found {len(shape_aspects)} Shape Aspects")
        else:
            logging.debug("HasShapeAspects exists but is empty.")
    else:
        logging.debug("No IFCSHAPEASPECTs found or 'HasShapeAspects' does not exist.")

    cells = []

    for shape_aspect in shape_aspects:
    
        ### Gather Informations of specific Layer

        material = shape_aspect.Name

        for representation in shape_aspect.ShapeRepresentations:
            if representation.is_a('IFCSHAPEREPRESENTATION'):
                # Iterate through items in the shape representation
                for item in representation.Items:
                    if item.is_a('IFCEXTRUDEDAREASOLID'):
                        # Get extrusion depth of the layer
                        layer_extrusion_depth = item.Depth

                        # Get location, axis, and reference direction of the extrusion
                        if item.Position.is_a('IFCAXIS2PLACEMENT3D'):
                            layer_axis_placement = item.Position
                            layer_location = layer_axis_placement.Location
                            layer_ref_direction = layer_axis_placement.RefDirection.DirectionRatios if layer_axis_placement.RefDirection else (1.0, 0.0, 0.0)
                            layer_axis_direction = layer_axis_placement.Axis.DirectionRatios if layer_axis_placement.Axis else (0.0, 0.0, 1.0)
                        else:
                            logging.debug("No valid IFCAXIS2PLACEMENT3D found.")

                        # Get extrusion direction
                        layer_extruded_direction = item.ExtrudedDirection.DirectionRatios

                        # Get the profile definition type and handle specific profile types
                        profile = item.SweptArea
                        layer_profile_type = profile.is_a()
                        logging.debug(f"Profile Type: {layer_profile_type}")

                        if layer_profile_type == 'IfcArbitraryClosedProfileDef':
                            # Retrieve points for the outer curve of the profile
                            if hasattr(profile, 'OuterCurve') and profile.OuterCurve.is_a('IFCINDEXEDPOLYCURVE'):
                                indexed_polycurve = profile.OuterCurve
                                if hasattr(indexed_polycurve, 'Points') and indexed_polycurve.Points.is_a('IFCCARTESIANPOINTLIST2D'):
                                    point_list_2d = indexed_polycurve.Points
                                    points = point_list_2d.CoordList

                        elif layer_profile_type == 'IfcArbitraryProfileDefWithVoids':
                            # Retrieve points for the outer curve when profile has voids
                            # Here "InnerCurve" is neglected because, our Goal can be achieved without these Openings
                            if hasattr(profile, 'OuterCurve') and profile.OuterCurve.is_a('IFCINDEXEDPOLYCURVE'):
                                indexed_polycurve = profile.OuterCurve
                                if hasattr(indexed_polycurve, 'Points') and indexed_polycurve.Points.is_a('IFCCARTESIANPOINTLIST2D'):
                                    point_list_2d = indexed_polycurve.Points
                                    points = point_list_2d.CoordList
                            else:
                                logging.debug("No valid OuterCurve or Points found for IFCARBITRARYPROFILEDEFWITHVOIDS")
                        else:
                            logging.debug("Profile definition is neither IfcArbitraryClosedProfileDef nor IfcArbitraryProfileDefWithVoids")
                    else:
                        logging.debug("Item is not IFCEXTRUDEDAREASOLID")
            else:
                logging.debug("Shape aspect does not have correct IFCSHAPEREPRESENTATION")

        # Output wall  details
        logging.debug("----WALL----")
        logging.debug("Location (IFCCARTESIANPOINT): %s", wall_rel_placement)
        logging.debug("Axis (IFCDIRECTION): %s", wall_axis)
        logging.debug("RefDirection (IFCCARTESIANPOINT): %s", wall_ref_direction)

        logging.debug("----LAYER----")
        logging.debug("Extrusion Depth: %s", layer_extrusion_depth)
        logging.debug("Material: %s", material)
        logging.debug("Location (IFCCARTESIANPOINT): %s", layer_location.Coordinates)
        logging.debug("Axis (IFCDIRECTION): %s", layer_axis_direction)
        logging.debug("RefDirection (IFCDIRECTION): %s", layer_ref_direction) 
        logging.debug("Extruded Direction (IFCDIRECTION): %s", layer_extruded_direction)

        # Output the coordinates of the vertices defining the profile
        logging.debug("----VERTICES----")
        for point in points:
            logging.debug(point)

        ### Align Element in Local CoordSystem

        # Apply the rotation matrix
        rotation_matrix = create_rotation_matrix(layer_axis_direction, layer_ref_direction)

        # Ensure points are rotated and translated 
        local_points = []
        for point in points:
            point_3d = np.array([point[0], point[1], 0.0])  # Embed 2D point into 3D
            rotated_point = rotation_matrix.dot(point_3d)   # Apply the rotation matrix
            translated_point = rotated_point + layer_location.Coordinates  # Translate based on layer location
            local_points.append(translated_point)

        # Transform Extrusion Direction
        extruded_direction_vector = np.array(layer_extruded_direction)
        transformed_extruded_direction = np.dot(rotation_matrix, extruded_direction_vector)

        logging.debug("Calculated local points after rotation and translation:")
        for p in local_points:
            logging.debug(p)

        logging.debug("Transformierter Extrusionsvektor:")
        logging.debug(transformed_extruded_direction)

        ### Build Topology

        # Convert the calculated points to vertices
        vertices = [Vertex.ByCoordinates(x, y, z) for x, y, z in local_points]

        # Create a face using the vertices
        face = Face.ByVertices(vertices)
        face_normal = Face.Normal(face)

        # Output to confirm the face and its normal vector have been created
        logging.debug(face)
        logging.debug(face_normal)

        # Normalize the face normal and extrusion direction to ensure correct dot product calculation
        face_normal = face_normal / np.linalg.norm(face_normal)
        extrusion_direction = np.array(transformed_extruded_direction)
        extrusion_direction = extrusion_direction / np.linalg.norm(extrusion_direction)

        # Calculate the dot product between the face normal and the extrusion direction
        dot_product = np.dot(face_normal, extrusion_direction)

        # Determine if the face extrusion needs to be reversed based on the dot product
        # Adjustment of threshold to handle floating-point precision issues
        reverse = dot_product < -0.9999

        logging.debug("Face Normal: %s", face_normal)
        logging.debug("Extrusion Direction: %s", extrusion_direction)
        logging.debug("Dot Product: %s", dot_product)
        logging.debug("Reverse: %s", reverse)

        # Create cell by extruding the face with specified thickness
        cell = Cell.ByThickenedFace(face, thickness=layer_extrusion_depth, bothSides=False, reverse=reverse)

        # Output to confirm that the cell has been created
        logging.debug("Cell created: %s", cell)

        Topology.AddDictionary(cell,Dictionary.ByKeyValue("material",material))


        ### Transformation from local CoordSystem to ProjectCoordSystem

        rotation_matrix = create_rotation_matrix(wall_axis, wall_ref_direction)
        axis, angle = rotation_matrix_to_axis_angle(rotation_matrix)

        # Test if Vector is Null
        if np.allclose(axis, [0, 0, 0]) and np.isclose(angle, 0):
            # No Rotation needed
            logging.debug("Keine Rotation erforderlich.")
            rotated_topology = cell  # No changes
        elif np.allclose(axis, [0, 0, 0]) and np.isclose(angle, 180):
            # Special Case "Mirroring"
            logging.debug("Sonderfall 180-Grad-Rotation erkannt.")
            rotation_axis = [0, 0, 1]  # Define a axis
            rotation_angle = 180  # 

            # Rotate
            rotated_topology = Topology.Rotate(
                cell,
                Vertex.ByCoordinates(0, 0, 0),
                rotation_axis,
                rotation_angle
            )
        else:
            # Standard Case
            rotation_axis = axis.tolist()
            rotation_angle = angle

            # Rotate
            rotated_topology = Topology.Rotate(
                cell,
                Vertex.ByCoordinates(0, 0, 0),
                rotation_axis,
                rotation_angle
            )

        # Translate rotated topology to the wall's relative placement
        final_topology = Topology.Translate(
            rotated_topology, 
            x=wall_rel_placement[0], 
            y=wall_rel_placement[1], 
            z=wall_rel_placement[2]
        )

        # Output the transformed topology to verify the translation
        logging.debug("Transformed Topology: %s", final_topology)

        cells.append(final_topology)

    if cells != []:
        # Create cell complex, add Info and add to cluster
        complex = CellComplex.ByCells(cells)
        topo_walls.append(complex)
        print(i)
    
    i += 1

#print(f"{len(topo_walls)} Walls from {len(wall_guids)} sucessfuly constructed")
topo_cluster = Cluster.ByTopologies(topo_walls)  # Combine all cell complexes into one cluster

###################################################################







