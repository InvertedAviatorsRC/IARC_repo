--[[
Author: Inverted Aviators RC
Year: 2024

This script mixes with a channel to rapidly 
change the output value between 1000 and 2000.

Put this `.lua` script in the `SCRIPTS/MIXES/` folder.
This file name can only be 6 characters long: `xxxxxx.lua`
]]--

-- Tell the TX to read in the value `Input` from a channel.
-- `SOURCE` can be any value that EdgeTX knows.
local inputs = {{ "Input", SOURCE }}

-- Variable name displayed on the TX.
-- Note: This can be named anything.
local outputs = { "GunVal" }

local function run(i)
  --[[
  -1000 = `Min PPM value` = 1000 on TX
  0 = `Middle PPM value` = 1500 on TX
  1000 = `Max PPM value` = 2000 on TX
  ]]--

  if i == 0 then
    return 1000
  elseif i == 1000 then
    return -1000
  elseif i == -1000 then
    return 1000
  end
  
end

return { input=inputs, output=outputs, run=run }
