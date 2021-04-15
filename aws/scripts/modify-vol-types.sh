 #!/bin/bash -xe

POSITIONAL=()

while [[ $# -gt 0 ]]; do
key="$1"

	case $key in
		-r|--region)
	    region="$2"
	    shift # past argument
	    shift # past value
	    ;;
	    -t|--tagname)
	    vName="$2"
	    shift # past argument
	    shift # past value
	    ;;
	    -o|--oldtype)
	    vOldType="$2"
	    shift # past argument
	    shift # past value
	    ;;
	    -n|--newtype)
	    vNewType="$2"
	    shift # past argument
	    shift # past value
	    ;;
	    *)    # unknown option
	    POSITIONAL+=("$1") # save it in an array for later
	    shift # past argument
	    ;;
	esac
done
set -- "${POSITIONAL[@]}" # restore positional parameters

echo ""

if [ -z "$region" ]; then
	echo "	MISSING Parameter: Region is required, like us-west-2"
	fail="true"
else
	echo "	*AWS Region = $region"
fi

if [ -z "$vName" ]; then
	echo "	MISSING Parameter: Tag Name is required, cut and paste from AWS EC2 Volumes Console View"
	fail="true"
else
	echo "	*Volume Tag Name = $vName"
fi

if [ -z "$vOldType" ]; then
	echo "	MISSING Parameter: Current Volume Type is required: gp2, gp3, sc1, st1"
	fail="true"
else
	echo "	*Old Volume Type = $vOldType"
fi

if [ -z "$vNewType" ]; then
	echo "	MISSING Parameter: New Volume Type is required: gp2, gp3, sc1, st1"
	fail="true"
else
	echo "	*New Volume Type = $vNewType"
fi

echo ""

if [ "$vOldType" = "gp2" ] && [ "$vNewType" = "gp3" ]; then
	echo "	--Changing gp2 -> gp3"
elif [ "$vOldType" = "gp3" ] && [ "$vNewType" = "gp2" ]; then
	echo "	--Changing gp3 -> gp2"
elif [ "$vOldType" = "sc1" ] && [ "$vNewType" = "st1" ]; then
	echo "	--Changing sc1 -> st1"
elif [ "$vOldType" = "st1" ] && [ "$vNewType" = "sc1" ]; then
	echo "	--Changing st1 -> sc1"
else
	echo "	**Can Only change between gp2 and gp3, or visa versa, and sc1 and st1, or visa versa. Review inputs."
	fail="true"
fi

if [ -z "$fail" ]; then
	echo "	--Finding $vOldType EBS Volumes With Tag Name= $vName"
else
	echo "	***COMMAND Structure: modify-vol-types.sh --region <aws region> --tagname <name> --oldtype <ebs vol type> --newtype <ebs vol type>"
	echo "  ***This script is designed to work with Qumulo SA Cloud Formation or Terraform provisioning scripts that generated EBS Volume Tags"
	exit
fi

volIds+=($(aws ec2 describe-volumes --region "$region" --filter "Name=tag:Name, Values=$vName" "Name=volume-type, Values=$vOldType" --query "Volumes[].VolumeId" --out "text"))

if [ ${#volIds} -eq 0 ]; then
	echo "	**No $vOldType EBS Volumes found with Tag Name= $vName"
	exit
else
	echo "	--Modifying ${#volIds[@]} Volumes from $vOldType to $vNewType"
fi

subTag=${vName%???}

for m in "${!volIds[@]}"; do
	aws ec2 modify-volume --region "$region" --volume-type "$vNewType" --volume-id "${volIds[m]}"
	aws ec2 create-tags --region "$region" --resources "${volIds[m]}" --tags "Key=Name,Value=$subTag$vNewType"
done 

