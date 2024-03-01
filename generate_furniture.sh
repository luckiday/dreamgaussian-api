#!/bin/bash

# Define arrays of furniture types and attributes
furniture_types=("sofa")
colors=("black" "white" "brown")
sizes=("tall" "short")

# Define the base command structure
base_command1="python main.py --config configs/text_viv.yaml"
base_command2="python main2.py --config configs/text_viv.yaml"

# Loop through the furniture types, colors, and sizes to generate commands
for furniture in "${furniture_types[@]}"; do
    for color in "${colors[@]}"; do
        for size in "${sizes[@]}"; do
            # Define the prompt and save_path
            prompt="${size} ${color}_${furniture}"
            save_path="${size}_${color}_${furniture}_001"

            # Generate and execute the commands
            command1="${base_command1} prompt=\"${prompt}\" save_path=\"${save_path}\""
            command2="${base_command2} prompt=\"${prompt}\" save_path=\"${save_path}\""

            echo "Executing: $command1"
            eval $command1

            echo "Executing: $command2"
            eval $command2
        done
    done
done
