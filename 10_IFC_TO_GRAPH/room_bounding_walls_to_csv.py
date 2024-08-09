import ifcopenshell
import csv

def main(ifc_file, target_storey, filtered_spaces):

    # Initialize a list to store the results
    space_to_walls = []

    # Process each filtered space
    for space in filtered_spaces:
        space_guid = space.GlobalId

        # Find the IfcRelSpaceBoundary relationships
        walls = []
        for rel_space_boundary in ifc_file.by_type("IfcRelSpaceBoundary"):
            if rel_space_boundary.RelatingSpace == space:
                if rel_space_boundary.RelatedBuildingElement and rel_space_boundary.RelatedBuildingElement.is_a("IfcWall"):
                    wall_guid = rel_space_boundary.RelatedBuildingElement.GlobalId
                    walls.append(wall_guid)

        # Append the collected data to the list
        space_to_walls.append({
            "space_guid": space_guid,
            "walls": walls
        })

        # Print the summary statement for each space
        print(f"Space ({space_guid}) analysed - Found {len(walls)} Walls")

    # Write the results to a CSV file (without header and space names)
    with open('Output04_RoomBoundingWalls.csv', 'w', newline='') as csvfile:
        csvwriter = csv.writer(csvfile, delimiter=';')
        for entry in space_to_walls:
            csvwriter.writerow([
                entry["space_guid"],
                ",".join(entry["walls"])
            ])

    print("Results have been successfully saved to Output04_RoomBoundingWalls.csv")

if __name__ == "__main__":
    main()
