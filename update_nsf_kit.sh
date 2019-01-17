# bash
JQKit_Path="$HOME/Documents/Workbench/JD/JQKit-iOS/"
JQKit_Source_Path="$JQKit_Path/JQKit/Classes"
JQKit_Fastlane_Path="$JQKit_Path/fastlane/Fastfile"
JQKit_Tests="$JQKit_Path/Example/Tests"

NSFKit_Path="$HOME/Documents/Github/NSFKit"
NSFKit_Source_Path="$NSFKit_Path/NSFKit/Classes"
NSFKit_Fastlane_Path="$NSFKit_Path/fastlane/Fastfile"
NSFKit_Tests="$NSFKit_Path/Example/Tests"

Source_Prefix="JQ"
Dest_Prefix="NSF"

# 同步源码
rm -rf $NSFKit_Source_Path
cp -r $JQKit_Source_Path $NSFKit_Source_Path

find $NSFKit_Source_Path -exec rename -S $Source_Prefix $Dest_Prefix {} +
grep -rl $Source_Prefix $NSFKit_Source_Path | xargs sed -i "" "s/$Source_Prefix/$Dest_Prefix/g"
grep -rl $Dest_Prefix $NSFKit_Source_Path | xargs sed -i "" "s/jq/nsf/g"

# 同步单元测试代码
find $NSFKit_Tests -name '*Spec.*' -type f -delete
find $JQKit_Tests -name '*Spec.*' -exec cp {} $NSFKit_Tests \;

find $NSFKit_Tests -exec rename -S $Source_Prefix $Dest_Prefix {} +
grep -rl $Source_Prefix $NSFKit_Tests | xargs sed -i "" "s/$Source_Prefix/$Dest_Prefix/g"
grep -rl $Dest_Prefix $NSFKit_Tests | xargs sed -i "" "s/jq/nsf/g"

# 同步 fastlane
cp $JQKit_Fastlane_Path $NSFKit_Fastlane_Path