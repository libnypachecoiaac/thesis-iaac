import ifcopenshell
import csv


def main(ifc_file, target_storey):
    # Initialize a list to store the results
    elements_to_walls = []

    # Function to find the hosting wall for an opening element
    def find_hosting_wall(opening_element):
        for rel_voids in ifc_file.by_type("IfcRelVoidsElement"):
            if rel_voids.RelatedOpeningElement == opening_element:
                return rel_voids.RelatingBuildingElement
        return None

    # Find all IfcDoors and IfcWindows in the target storey
    for rel_contained in target_storey.ContainsElements:
        for element in rel_contained.RelatedElements:
            if element.is_a("IfcDoor") or element.is_a("IfcWindow"):
                element_type = element.is_a()
                element_guid = element.GlobalId

                # Find the IfcRelFillsElement relationships
                target_opening = None
                for rel_fills in ifc_file.by_type("IfcRelFillsElement"):
                    if rel_fills.RelatedBuildingElement == element:
                        target_opening = rel_fills.RelatingOpeningElement
                        break

                if target_opening:
                    # Find the hosting wall
                    hosting_wall = find_hosting_wall(target_opening)
                    if hosting_wall:
                        wall_guid = hosting_wall.GlobalId
                        elements_to_walls.append({
                            "element_type": element_type,
                            "element_guid": element_guid,
                            "wall_guid": wall_guid
                        })

    # Write the results to a CSV file
    with open('Output05_Hosts_of_WindowsAndDoors.csv', 'w', newline='') as csvfile:
        csvwriter = csv.writer(csvfile, delimiter=';')
        for entry in elements_to_walls:
            csvwriter.writerow([entry["element_type"], entry["element_guid"], entry["wall_guid"]])

    print("Data has been written to Output05_Hosts_of_WindowsAndDoors.csv")


if __name__ == "__main__":
    main()
