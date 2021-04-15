#!/bin/bash

af_disk=(
	[1]=af_6x100gib
	[2]=af_8x128gib 
	[3]=af_10x500gib 
	[4]=af_16x512gib 
	[5]=af_25x533gib 
	[6]=af_25x820gib 
	[7]=af_8x3750gib
	[8]=af_25x1434gib 
	[9]=af_25x2253gib
)

af_cap=(
	[1]=600GiB
	[2]=1TB
	[3]=5TB
	[4]=8TiB
	[5]=13TiB
	[6]=20TiB
	[7]=30TB
	[8]=35TiB
	[9]=55TiB
)

hybrid_disk=(
	[1]=hybrid_10x500gib_5x100gib
	[2]=hybrid_8x1024gib_4x150gib
	[3]=hybrid_8x1664gib_4x175gib
	[4]=hybrid_10x2000gib_5x160gib
	[5]=hybrid_10x3584gib_5x350gib
	[6]=hybrid_10x5632gib_5x550gib
	[7]=hybrid_10x9216gib_5x900gib
	[8]=hybrid_16x10240gib_8x1000gib
	[9]=hybrid_16x16384gib_8x1600gib
	[10]=hybrid_20x16384gib_5x2500gib
)

hybrid_cap=(
	[1]=5TB
	[2]=8TiB
	[3]=13TiB
	[4]=20TB
	[5]=35TiB
	[6]=55TiB
	[7]=90TiB
	[8]=160TiB
	[9]=256TiB
	[10]=320TiB
)

for n in {4..10}; do
	echo "*** Generating ${n}x Node Configurations ***"
  	
  	if [ $n -eq 4 ]; then
  		echo "List of Generated Configs" > output_config_list.txt
  	fi

	echo "	* All Flash Configs *"	
	for m in "${!af_disk[@]}"; do 
		python3 generate-qumulo-cloudformation-template-SA.py --num-nodes ${n} --config-file standard_drive_configs/${af_disk[$m]}.json  > ./cluster_configs/${n}x${af_cap[$m]}-AF-SA.cft.json
		echo "		-${n}x${af_cap[$m]}-AF-SA"
		echo "- ${n}x${af_cap[$m]}-AF-SA" >> output_config_list.txt
	done

	echo "	* Hybrid st-1 Configs *"	
	for m in "${!hybrid_disk[@]}"; do 
		python3 generate-qumulo-cloudformation-template-SA.py --num-nodes ${n} --config-file standard_drive_configs/${hybrid_disk[$m]}.json --backing-volume-type-override st1 > ./cluster_configs/${n}x${hybrid_cap[$m]}-Hybrid-st1-SA.cft.json
		echo "		-${n}x${hybrid_cap[$m]}-Hybrid-st1-SA"
		echo "- ${n}x${hybrid_cap[$m]}-Hybrid-st1-SA" >> output_config_list.txt
	done

	echo "	* Hybrid sc-1 Configs *"	
	for m in "${!hybrid_disk[@]}"; do 
		if [ $m -gt 1 ]; then
			python3 generate-qumulo-cloudformation-template-SA.py --num-nodes ${n} --config-file standard_drive_configs/${hybrid_disk[$m]}.json --backing-volume-type-override sc1 > ./cluster_configs/${n}x${hybrid_cap[$m]}-Hybrid-sc1-SA.cft.json
			echo "		-${n}x${hybrid_cap[$m]}-Hybrid-sc1-SA"
			echo "- ${n}x${hybrid_cap[$m]}-Hybrid-sc1-SA" >> output_config_list.txt
		fi
	done

done






