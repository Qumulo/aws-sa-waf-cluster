getqq () {
  local ip=$1 file_name=$2

  wget --no-check-certificate -O $file_name https://$ip/static/qq
  chmod 777 ./$file_name
}

getsecret () {
  local filter=$1 arn=$2 region=$3 obscure=$4
  local secret
  
  if [ "$obscure" == "true" ]; then
    secret=$(aws secretsmanager get-secret-value --region $region --query "SecretString" --output text --secret-id $arn | jq -r .$filter | xxd -p -r)
  else
    secret=$(aws secretsmanager get-secret-value --region $region --query "SecretString" --output text --secret-id $arn | jq -r .$filter)
  fi
  echo $secret
}

ssmput () {
  local key=$1 region=$2 stackname=$3 value=$4
  aws ssm put-parameter --region $region --type String --overwrite --name "/qumulo/$stackname/$key" --value "$value"
}

ssmget () {
  local key=$1 region=$2 stackname=$3
  local output
  output=$(aws ssm get-parameter --region $region --output text --name "/qumulo/$stackname/$key" --query "Parameter.Value")
  echo $output
}

stackprotect () {
  local enable=$1 region=$2 stackname=$3

  if [ "$enable" == "NO" ]; then
    aws cloudformation update-termination-protection --region $region --stack-name $stackname --no-enable-termination-protection
  else
    aws cloudformation update-termination-protection --region $region --stack-name $stackname --enable-termination-protection
  fi
}

ec2protect () {
  local enable=$1 region=$2 instance=$3
  if [ "$enable" == "NO" ]; then
    aws ec2 modify-instance-attribute --region $region --instance-id $instance --no-disable-api-termination
  else
    aws ec2 modify-instance-attribute --region $region --instance-id $instance --disable-api-termination
  fi    
}

vercomp () {        
  if [[ $1 == $2 ]]; then
    return 0
  fi

  local IFS=.
  local i v1=($1) v2=($2)

  for ((i=${#v1[@]}; i<${#v2[@]}; i++)); do
    v1[i]=0
  done
  for ((i=0; i<${#v1[@]}; i++)); do
    if [[ -z ${v2[i]} ]]; then
      v2[i]=0
    fi
    if ((10#${v1[i]} > 10#${v2[i]})); then
      return 2
    fi
    if ((10#${v1[i]} < 10#${v2[i]})); then
      return 1
    fi
  done
  return 0
}

modcmkpolicy () {
  local cmk=$1 region=$2 stackname=$3 new_vpc=$4 sc_lid=$5 cq_lid=$6 lam_lid=$7 
  local m sc_arn="" tag_name sc_name sub sc_stackname sc_stack_id cloudq_stack_id arn_list=() output
  while [ -z "$sc_arn" ]; do
    echo "Gathering info for Lambda IAM Role..."      
    if [ "$new_vpc" == "NO" ]; then
      sc_stack_id=$(aws cloudformation describe-stack-resource --region $region --stack-name $stackname --logical-resource-id $sc_lid --query StackResourceDetail.PhysicalResourceId --output text) || output="error"
    else
      cloudq_stack_id=$(aws cloudformation describe-stack-resource --region $region --stack-name $stackname --logical-resource-id $cq_lid --query StackResourceDetail.PhysicalResourceId --output text) || output="error"
      sc_stack_id=$(aws cloudformation describe-stack-resource --region $region --stack-name $cloudq_stack_id --logical-resource-id $sc_lid --query StackResourceDetail.PhysicalResourceId --output text) || output="error" 
    fi

    sc_stackname=$(aws cloudformation describe-stack-resource --region $region --stack-name $sc_stack_id --logical-resource-id $lam_lid --query StackResourceDetail.StackName --output text) || output="error"

    if [ "$output" == "error" ]; then
      echo "..waiting for lambda to deploy"
      sleep 10            
    else
      sub='.Functions[] | select(.FunctionName|test(".'$lam_lid'.")) | .FunctionArn'

      read -r -a arn_list <<< $(aws lambda list-functions --region $region | jq -r "$sub")
      for m in ${!arn_list[@]}; do
        tag_name=$(aws lambda list-tags --region $region --resource "${arn_list[m]}" | jq -r '.Tags."aws:cloudformation:stack-name"')
        if [ "$tag_name" == "$sc_stackname" ]; then
          sc_arn=$(aws lambda get-function --region $region --function-name "${arn_list[m]}"| jq -r .Configuration.Role)
          break
        fi
      done    
    fi
  done

  echo $sc_arn | grep -o ".*/" | tr -d "/" > ./role.txt
  echo $sc_arn | grep -o "/.*" | tr -d "/" > ./lambda.txt
  sed "s/ROLE/$(cat ./role.txt)/g" ./add_policy.json > ./add_policy2.json
  sed "s/LAMBDA/$(cat ./lambda.txt)/g" ./add_policy2.json > ./add_policy3.json
  aws kms get-key-policy --region $region --key-id $cmk --policy-name default --output text > ./def_policy.json
  head -n -2 ./def_policy.json > ./new_policy.json
  cat ./add_policy3.json >> ./new_policy.json
  aws kms put-key-policy --region $region --key-id $cmk --policy-name default --policy file://./new_policy.json
}

tagvols () {
  local id_list_name=$1[@] region=$2 stack_name=$3 
  local m id_list bootIDs=() gp2IDs=() gp3IDs=() st1IDs=() sc1IDs=()

  id_list=("${!id_list_name}")

  for m in "${!id_list[@]}"; do 
    bootIDs+=($(aws ec2 describe-volumes --region $region --filter "Name=attachment.instance-id, Values=${id_list[m]}" "Name=attachment.device, Values=/dev/sda*" --query "Volumes[].VolumeId" --out "text"))
    gp2IDs+=($(aws ec2 describe-volumes --region $region --filter "Name=attachment.instance-id, Values=${id_list[m]}" "Name=attachment.device, Values=/dev/x*" "Name=volume-type, Values=gp2" --query "Volumes[].VolumeId" --out "text"))
    gp3IDs+=($(aws ec2 describe-volumes --region $region --filter "Name=attachment.instance-id, Values=${id_list[m]}" "Name=attachment.device, Values=/dev/x*" "Name=volume-type, Values=gp3" --query "Volumes[].VolumeId" --out "text"))
    st1IDs+=($(aws ec2 describe-volumes --region $region --filter "Name=attachment.instance-id, Values=${id_list[m]}" "Name=attachment.device, Values=/dev/x*" "Name=volume-type, Values=st1" --query "Volumes[].VolumeId" --out "text"))
    sc1IDs+=($(aws ec2 describe-volumes --region $region --filter "Name=attachment.instance-id, Values=${id_list[m]}" "Name=attachment.device, Values=/dev/x*" "Name=volume-type, Values=sc1" --query "Volumes[].VolumeId" --out "text"))                           
  done

  for m in "${!bootIDs[@]}"; do
    aws ec2 create-tags --region $region --resources ${bootIDs[m]} --tags "Key=Name,Value=$stack_name-boot"
  done 
  for m in "${!gp2IDs[@]}"; do
    aws ec2 create-tags --region $region --resources ${gp2IDs[m]} --tags "Key=Name,Value=$stack_name-gp2"
  done 
  for m in "${!gp3IDs[@]}"; do
    aws ec2 create-tags --region $region --resources ${gp3IDs[m]} --tags "Key=Name,Value=$stack_name-gp3"
  done 
  for m in "${!st1IDs[@]}"; do
    aws ec2 create-tags --region $region --resources ${st1IDs[m]} --tags "Key=Name,Value=$stack_name-st1"
  done 
  for m in "${!sc1IDs[@]}"; do
    aws ec2 create-tags --region $region --resources ${sc1IDs[m]} --tags "Key=Name,Value=$stack_name-sc1"
  done
}