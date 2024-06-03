# Author Inverted Aviators RC

local inputs = {{ "Input", SOURCE }}

local outputs = { "GunVal" }

local function run(i)
  
  if i == 0 then
    return 1000
  elseif i == 1000 then
    return -1000
  elseif i == -1000 then
    return 1000
  end
    
end

return { input=inputs, output=outputs, run=run }

