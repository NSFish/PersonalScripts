#! /bin/sh

IFS=$'\n'

for d in $(find . -mindepth 1 -type d)  
do   
    cd $d
    rename -N "...01" -X -e '$_ = "$N"' *
    cd ..
done