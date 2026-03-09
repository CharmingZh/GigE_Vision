import sys
import os
import eBUS as ebus

def main():
    system = ebus.PvSystem()
    system.Find()
    
    device_info = None
    for i in range(system.GetInterfaceCount()):
        interface = system.GetInterface(i)
        for j in range(interface.GetDeviceCount()):
            di = interface.GetDeviceInfo(j)
            model_name = di.GetModelName().GetAscii()
            print(f"Found: {model_name}")
            if "FS-3200" in model_name:
                device_info = di
                break
        if device_info:
            break
            
    if not device_info:
        print("Device not found.")
        return
        
    result, device = ebus.PvDevice.CreateAndConnect(device_info)
    if not result.IsOK():
        print("Failed to connect.")
        return
        
    params = device.GetParameters()
    
    # Let's search for parameters related to MultiPart, Source, Channel, etc.
    with open("params.txt", "w") as f:
        for i in range(params.GetCount()):
            param = params.Get(i)
            res, name = param.GetName()
            if res.IsOK():
                try:
                    res2, val = param.ToString()
                    if res2.IsOK():
                        f.write(f"{name}: {val}\n")
                except:
                    pass
                
    device.Disconnect()
    ebus.PvDevice.Free(device)

if __name__ == "__main__":
    main()
