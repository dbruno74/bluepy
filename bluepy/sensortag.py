from bluepy.btle import UUID, Peripheral, DefaultDelegate, AssignedNumbers
import struct
import math
import signal
import sys
import threading
   
def _TI_UUID(val):
    return UUID("%08X-0451-4000-b000-000000000000" % (0xF0000000+val))

# Sensortag versions
AUTODETECT = "-"
SENSORTAG_V1 = "v1"
SENSORTAG_2650 = "CC2650"
SENSORTAG_1352R = "CC1352R"

class SensorBase:
    # Derived classes should set: svcUUID, ctrlUUID, dataUUID
    sensorOn  = struct.pack("B", 0x01)
    sensorOff = struct.pack("B", 0x00)

    def __init__(self, periph):
        self.periph = periph
        self.service = None
        self.ctrl = None
        self.data = None

    def enable(self):
        if self.service is None:
            self.service = self.periph.getServiceByUUID(self.svcUUID)
        if self.ctrl is None:
            self.ctrl = self.service.getCharacteristics(self.ctrlUUID) [0]
        if self.data is None:
            self.data = self.service.getCharacteristics(self.dataUUID) [0]
        if self.sensorOn is not None:
            self.ctrl.write(self.sensorOn,withResponse=True)

    def read(self):
        return self.data.read()

    def disable(self):
        if self.ctrl is not None:
            self.ctrl.write(self.sensorOff)

    # Derived class should implement _formatData()

def calcPoly(coeffs, x):
    return coeffs[0] + (coeffs[1]*x) + (coeffs[2]*x*x)

class IRTemperatureSensor(SensorBase):
    svcUUID  = _TI_UUID(0xAA00)
    dataUUID = _TI_UUID(0xAA01)
    ctrlUUID = _TI_UUID(0xAA02)

    zeroC = 273.15 # Kelvin
    tRef  = 298.15
    Apoly = [1.0,      1.75e-3, -1.678e-5]
    Bpoly = [-2.94e-5, -5.7e-7,  4.63e-9]
    Cpoly = [0.0,      1.0,      13.4]

    def __init__(self, periph):
        SensorBase.__init__(self, periph)
        self.S0 = 6.4e-14

    def read(self):
        '''Returns (ambient_temp, target_temp) in degC'''

        # See http://processors.wiki.ti.com/index.php/SensorTag_User_Guide#IR_Temperature_Sensor
        (rawVobj, rawTamb) = struct.unpack('<hh', self.data.read())
        tAmb = rawTamb / 128.0
        Vobj = 1.5625e-7 * rawVobj

        tDie = tAmb + self.zeroC
        S   = self.S0 * calcPoly(self.Apoly, tDie-self.tRef)
        Vos = calcPoly(self.Bpoly, tDie-self.tRef)
        fObj = calcPoly(self.Cpoly, Vobj-Vos)

        tObj = math.pow( math.pow(tDie,4.0) + (fObj/S), 0.25 )
        return (tAmb, tObj - self.zeroC)


class IRTemperatureSensorTMP007(SensorBase):
    svcUUID  = _TI_UUID(0xAA00)
    dataUUID = _TI_UUID(0xAA01)
    ctrlUUID = _TI_UUID(0xAA02)

    SCALE_LSB = 0.03125;
 
    def __init__(self, periph):
        SensorBase.__init__(self, periph)

    def read(self):
        '''Returns (ambient_temp, target_temp) in degC'''
        # http://processors.wiki.ti.com/index.php/CC2650_SensorTag_User's_Guide?keyMatch=CC2650&tisearch=Search-EN
        (rawTobj, rawTamb) = struct.unpack('<hh', self.data.read())
        tObj = (rawTobj >> 2) * self.SCALE_LSB;
        tAmb = (rawTamb >> 2) * self.SCALE_LSB;
        return (tAmb, tObj)
    
class TemperatureSensorHDC2010(SensorBase):
    svcUUID  = _TI_UUID(0xAA00)
    dataUUID = _TI_UUID(0xAA01)
    ctrlUUID = _TI_UUID(0xAA02)

    def __init__(self, periph):
        SensorBase.__init__(self, periph)

    def read(self):
        
        return (round(struct.unpack('<f', self.data.read())[0],2))
    
class AccelerometerSensor(SensorBase):
    svcUUID  = _TI_UUID(0xAA10)
    dataUUID = _TI_UUID(0xAA11)
    ctrlUUID = _TI_UUID(0xAA12)

    def __init__(self, periph):
        SensorBase.__init__(self, periph)
        if periph.firmwareVersion.startswith("1.4 "):
            self.scale = 64.0
        else:
            self.scale = 16.0

    def read(self):
        '''Returns (x_accel, y_accel, z_accel) in units of g'''
        x_y_z = struct.unpack('bbb', self.data.read())
        return tuple([ (val/self.scale) for val in x_y_z ])

class AccelerometerSensorADXL362(SensorBase):
    svcUUID  = _TI_UUID(0xFFA0)
    dataUUID = None
    ctrlUUID = _TI_UUID(0xFFA1)
    sensorOn = struct.pack("B",0x01)

    def __init__(self, periph):
        SensorBase.__init__(self, periph)
 
    def enable(self):
        SensorBase.enable(self)
        self.char_descr = self.service.getDescriptors(forUUID=0x2902)[0]
        self.char_descr.write(struct.pack('<bb', 0x01, 0x00), True)
        self.char_descr = self.service.getDescriptors(forUUID=0x2902)[1]
        self.char_descr.write(struct.pack('<bb', 0x01, 0x00), True)
        self.char_descr = self.service.getDescriptors(forUUID=0x2902)[2]
        self.char_descr.write(struct.pack('<bb', 0x01, 0x00), True)
        
    def disable(self):
        if self.service:
            self.char_descr = self.service.getDescriptors(forUUID=0x2902)[0]
            self.char_descr.write(struct.pack('<bb', 0x00, 0x00), True)
            self.char_descr = self.service.getDescriptors(forUUID=0x2902)[1]
            self.char_descr.write(struct.pack('<bb', 0x00, 0x00), True)
            self.char_descr = self.service.getDescriptors(forUUID=0x2902)[2]
            self.char_descr.write(struct.pack('<bb', 0x00, 0x00), True)
        SensorBase.disable(self)
    
class MovementSensorMPU9250(SensorBase):
    svcUUID  = _TI_UUID(0xAA80)
    dataUUID = _TI_UUID(0xAA81)
    ctrlUUID = _TI_UUID(0xAA82)
    sensorOn = None
    GYRO_XYZ =  7
    ACCEL_XYZ = 7 << 3
    MAG_XYZ = 1 << 6
    ACCEL_RANGE_2G  = 0 << 8
    ACCEL_RANGE_4G  = 1 << 8
    ACCEL_RANGE_8G  = 2 << 8
    ACCEL_RANGE_16G = 3 << 8

    def __init__(self, periph):
        SensorBase.__init__(self, periph)
        self.ctrlBits = 0

    def enable(self, bits):
        SensorBase.enable(self)
        self.ctrlBits |= bits
        self.ctrl.write( struct.pack("<H", self.ctrlBits) )

    def disable(self, bits):
        self.ctrlBits &= ~bits
        self.ctrl.write( struct.pack("<H", self.ctrlBits) )

    def rawRead(self):
        dval = self.data.read()
        return struct.unpack("<hhhhhhhhh", dval)

class AccelerometerSensorMPU9250:
    def __init__(self, sensor_):
        self.sensor = sensor_
        self.bits = self.sensor.ACCEL_XYZ | self.sensor.ACCEL_RANGE_4G
        self.scale = 8.0/32768.0 # TODO: why not 4.0, as documented?

    def enable(self):
        self.sensor.enable(self.bits)

    def disable(self):
        self.sensor.disable(self.bits)

    def read(self):
        '''Returns (x_accel, y_accel, z_accel) in units of g'''
        rawVals = self.sensor.rawRead()[3:6]
        return tuple([ v*self.scale for v in rawVals ])



class HumiditySensor(SensorBase):
    svcUUID  = _TI_UUID(0xAA20)
    dataUUID = _TI_UUID(0xAA21)
    ctrlUUID = _TI_UUID(0xAA22)

    def __init__(self, periph):
        SensorBase.__init__(self, periph)

    def read(self):
        '''Returns (ambient_temp, rel_humidity)'''
        (rawT, rawH) = struct.unpack('<HH', self.data.read())
        temp = -46.85 + 175.72 * (rawT / 65536.0)
        RH = -6.0 + 125.0 * ((rawH & 0xFFFC)/65536.0)
        return (temp, RH)

class HumiditySensorHDC1000(SensorBase):
    svcUUID  = _TI_UUID(0xAA20)
    dataUUID = _TI_UUID(0xAA21)
    ctrlUUID = _TI_UUID(0xAA22)

    def __init__(self, periph):
        SensorBase.__init__(self, periph)

    def read(self):
        '''Returns (ambient_temp, rel_humidity)'''
        (rawT, rawH) = struct.unpack('<HH', self.data.read())
        temp = -40.0 + 165.0 * (rawT / 65536.0)
        RH = 100.0 * (rawH/65536.0)
        return (temp, RH)
    
class HumiditySensorHDC2010(SensorBase):
    svcUUID  = _TI_UUID(0xAA20)
    dataUUID = _TI_UUID(0xAA21)
    ctrlUUID = _TI_UUID(0xAA22)

    def __init__(self, periph):
        SensorBase.__init__(self, periph)

    def read(self):
        
        return (round(struct.unpack('<f', self.data.read())[0],2))

class MagnetometerSensor(SensorBase):
    svcUUID  = _TI_UUID(0xAA30)
    dataUUID = _TI_UUID(0xAA31)
    ctrlUUID = _TI_UUID(0xAA32)

    def __init__(self, periph):
        SensorBase.__init__(self, periph)

    def read(self):
        '''Returns (x, y, z) in uT units'''
        x_y_z = struct.unpack('<hhh', self.data.read())
        return tuple([ 1000.0 * (v/32768.0) for v in x_y_z ])
        # Revisit - some absolute calibration is needed

class MagnetometerSensorMPU9250:
    def __init__(self, sensor_):
        self.sensor = sensor_
        self.scale = 4912.0 / 32760
        # Reference: MPU-9250 register map v1.4

    def enable(self):
        self.sensor.enable(self.sensor.MAG_XYZ)

    def disable(self):
        self.sensor.disable(self.sensor.MAG_XYZ)

    def read(self):
        '''Returns (x_mag, y_mag, z_mag) in units of uT'''
        rawVals = self.sensor.rawRead()[6:9]
        return tuple([ v*self.scale for v in rawVals ])

class BarometerSensor(SensorBase):
    svcUUID  = _TI_UUID(0xAA40)
    dataUUID = _TI_UUID(0xAA41)
    ctrlUUID = _TI_UUID(0xAA42)
    calUUID  = _TI_UUID(0xAA43)
    sensorOn = None

    def __init__(self, periph):
       SensorBase.__init__(self, periph)

    def enable(self):
        SensorBase.enable(self)
        self.calChr = self.service.getCharacteristics(self.calUUID) [0]

        # Read calibration data
        self.ctrl.write( struct.pack("B", 0x02), True )
        (c1,c2,c3,c4,c5,c6,c7,c8) = struct.unpack("<HHHHhhhh", self.calChr.read())
        self.c1_s = c1/float(1 << 24)
        self.c2_s = c2/float(1 << 10)
        self.sensPoly = [ c3/1.0, c4/float(1 << 17), c5/float(1<<34) ]
        self.offsPoly = [ c6*float(1<<14), c7/8.0, c8/float(1<<19) ]
        self.ctrl.write( struct.pack("B", 0x01), True )


    def read(self):
        '''Returns (ambient_temp, pressure_millibars)'''
        (rawT, rawP) = struct.unpack('<hH', self.data.read())
        temp = (self.c1_s * rawT) + self.c2_s
        sens = calcPoly( self.sensPoly, float(rawT) )
        offs = calcPoly( self.offsPoly, float(rawT) )
        pres = (sens * rawP + offs) / (100.0 * float(1<<14))
        return (temp,pres)

class BarometerSensorBMP280(SensorBase):
    svcUUID  = _TI_UUID(0xAA40)
    dataUUID = _TI_UUID(0xAA41)
    ctrlUUID = _TI_UUID(0xAA42)

    def __init__(self, periph):
        SensorBase.__init__(self, periph)

    def read(self):
        (tL,tM,tH,pL,pM,pH) = struct.unpack('<BBBBBB', self.data.read())
        temp = (tH*65536 + tM*256 + tL) / 100.0
        press = (pH*65536 + pM*256 + pL) / 100.0
        return (temp, press)

class GyroscopeSensor(SensorBase):
    svcUUID  = _TI_UUID(0xAA50)
    dataUUID = _TI_UUID(0xAA51)
    ctrlUUID = _TI_UUID(0xAA52)
    sensorOn = struct.pack("B",0x07)

    def __init__(self, periph):
       SensorBase.__init__(self, periph)

    def read(self):
        '''Returns (x,y,z) rate in deg/sec'''
        x_y_z = struct.unpack('<hhh', self.data.read())
        return tuple([ 250.0 * (v/32768.0) for v in x_y_z ])

class GyroscopeSensorMPU9250:
    def __init__(self, sensor_):
        self.sensor = sensor_
        self.scale = 500.0/65536.0

    def enable(self):
        self.sensor.enable(self.sensor.GYRO_XYZ)

    def disable(self):
        self.sensor.disable(self.sensor.GYRO_XYZ)

    def read(self):
        '''Returns (x_gyro, y_gyro, z_gyro) in units of degrees/sec'''
        rawVals = self.sensor.rawRead()[0:3]
        return tuple([ v*self.scale for v in rawVals ])

class KeypressSensor(SensorBase):
    svcUUID = UUID(0xFFE0)
    dataUUID = UUID(0xFFE1)
    ctrlUUID = None

    def __init__(self, periph):
        SensorBase.__init__(self, periph)
 
    def enable(self):
        SensorBase.enable(self)
        self.char_descr = self.service.getDescriptors(forUUID=0x2902)[0]
        self.char_descr.write(struct.pack('<bb', 0x01, 0x00), True)

    def disable(self):
        self.char_descr.write(struct.pack('<bb', 0x00, 0x00), True)
        
class KeypressSensorCC1352R(SensorBase):
    svcUUID = _TI_UUID(0x1120)
    dataUUID = _TI_UUID(0x1121)
    ctrlUUID = None
    sensorOn = None

    def __init__(self, periph):
        SensorBase.__init__(self, periph)
 
    def enable(self):
        SensorBase.enable(self)
        self.char_descr = self.service.getDescriptors(forUUID=0x2902)[0]
        self.char_descr.write(struct.pack('<bb', 0x01, 0x00), True)
        self.char_descr = self.service.getDescriptors(forUUID=0x2902)[1]
        self.char_descr.write(struct.pack('<bb', 0x01, 0x00), True)

    def disable(self):
        self.char_descr.write(struct.pack('<bb', 0x00, 0x00), True)

class OpticalSensorOPT3010(SensorBase):
    svcUUID  = _TI_UUID(0xAA70)
    dataUUID = _TI_UUID(0xAA71)
    ctrlUUID = _TI_UUID(0xAA72)

    def __init__(self, periph):
       SensorBase.__init__(self, periph)

    def read(self):
        '''Returns value in lux'''
        return (round(struct.unpack('<f', self.data.read())[0],2))
    
class OpticalSensorOPT3001(SensorBase):
    svcUUID  = _TI_UUID(0xAA70)
    dataUUID = _TI_UUID(0xAA71)
    ctrlUUID = _TI_UUID(0xAA72)

    def __init__(self, periph):
       SensorBase.__init__(self, periph)

    def read(self):
        '''Returns value in lux'''
        raw = struct.unpack('<h', self.data.read()) [0]
        m = raw & 0xFFF;
        e = (raw & 0xF000) >> 12;
        return 0.01 * (m << e)

class BatterySensor(SensorBase):
    svcUUID  = UUID("0000180f-0000-1000-8000-00805f9b34fb")
    dataUUID = UUID("00002a19-0000-1000-8000-00805f9b34fb")
    ctrlUUID = None
    sensorOn = None

    def __init__(self, periph):
       SensorBase.__init__(self, periph)

    def read(self):
        '''Returns the battery level in percent'''
        val = ord(self.data.read())
        return val

class BatterySensorCC1352R(SensorBase):
    svcUUID  = _TI_UUID(0x180f)
    dataUUID = _TI_UUID(0x2a19)
    ctrlUUID = None
    sensorOn = None

    def __init__(self, periph):
       SensorBase.__init__(self, periph)

    def read(self):
        '''Returns the battery level in percent'''
        val = ord(self.data.read())
        return val
    
class SensorTag(Peripheral):
    version = AUTODETECT
    
    def __init__(self,addr):
        Peripheral.__init__(self,addr)
        if self.version==AUTODETECT:
            svcs = self.discoverServices()
            if _TI_UUID(0xAA70) in svcs:
                if _TI_UUID(0xFFA0)in svcs: #ADXL362 Accelerometer 
                    self.version = SENSORTAG_1352R   
                else:
                    self.version = SENSORTAG_2650
            else:
                self.version = SENSORTAG_V1

        fwVers = self.getCharacteristics(uuid=AssignedNumbers.firmwareRevisionString)
        if len(fwVers) >= 1:
            self.firmwareVersion = fwVers[0].read().decode("utf-8")
        else:
            self.firmwareVersion = u''

        if self.version==SENSORTAG_V1:
            self.IRtemperature = IRTemperatureSensor(self)
            self.accelerometer = AccelerometerSensor(self)
            self.humidity = HumiditySensor(self)
            self.magnetometer = MagnetometerSensor(self)
            self.barometer = BarometerSensor(self)
            self.gyroscope = GyroscopeSensor(self)
            self.keypress = KeypressSensor(self)
            self.lightmeter = None
        elif self.version==SENSORTAG_2650:
            self._mpu9250 = MovementSensorMPU9250(self)
            self.IRtemperature = IRTemperatureSensorTMP007(self)
            self.accelerometer = AccelerometerSensorMPU9250(self._mpu9250)
            self.humidity = HumiditySensorHDC1000(self)
            self.magnetometer = MagnetometerSensorMPU9250(self._mpu9250)
            self.barometer = BarometerSensorBMP280(self)
            self.gyroscope = GyroscopeSensorMPU9250(self._mpu9250)
            self.keypress = KeypressSensor(self)
            self.lightmeter = OpticalSensorOPT3001(self)
            self.battery = BatterySensor(self)
        elif self.version==SENSORTAG_1352R:
            self._mpu9250 = None
            self.IRtemperature = TemperatureSensorHDC2010(self)
            self.accelerometer = AccelerometerSensorADXL362(self)
            self.humidity = HumiditySensorHDC2010(self)
            self.magnetometer = None
            self.barometer = None
            self.gyroscope = None
            self.keypress = KeypressSensorCC1352R(self)
            self.lightmeter = OpticalSensorOPT3010(self)
            self.battery = BatterySensorCC1352R(self)
            
class KeypressDelegate(DefaultDelegate):
    BUTTON_L = 0x02
    BUTTON_R = 0x01
    ALL_BUTTONS = (BUTTON_L | BUTTON_R)

    _button_desc = { 
        BUTTON_L : "Left button",
        BUTTON_R : "Right button",
        ALL_BUTTONS : "Both buttons"
    } 

    def __init__(self):
        DefaultDelegate.__init__(self)
        self.lastVal = 0

    def handleNotification(self, hnd, data):
        # NB: only one source of notifications at present
        # so we can ignore 'hnd'.
        val = struct.unpack("B", data)[0]
        down = (val & ~self.lastVal) & self.ALL_BUTTONS
        if down != 0:
            self.onButtonDown(down)
        up = (~val & self.lastVal) & self.ALL_BUTTONS
        if up != 0:
            self.onButtonUp(up)
        self.lastVal = val

    def onButtonUp(self, but):
        print ( "** " + self._button_desc[but] + " UP")

    def onButtonDown(self, but):
        print ( "** " + self._button_desc[but] + " DOWN")

class SensorDelegate(DefaultDelegate):
    BUTTON_L = 0x02
    BUTTON_R = 0x01
    BUTTON_HOLD = 0xB1
    
    _button_desc = { 
        BUTTON_L : "Button 2",
        BUTTON_R : "Button 1",
    } 

    def __init__(self, rnd):
        DefaultDelegate.__init__(self)
        self.lastVal = 0
        self.rnd = rnd


    def handleNotification(self, hnd, data):

        but = 0x00
        #Accelerometer
        
        if hnd == 110: #x-axis data
            self.x = struct.unpack('<h',data)[0]
        if hnd == 114: #y-axis data
            self.y = struct.unpack('<h',data)[0]
        if hnd == 118: #z-axis data
            self.z = struct.unpack('<h',data)[0]
            self.rnd.render ('Accelerometer: ', str(self.x) + ',' + str(self.y) + ',' + str(self.z),'')
        
        #Keypress

        if hnd == 90:
            but = 0x01
        if hnd == 94:
            but = 0x02

        if but != 0x00:        
            val = struct.unpack("B", data)[0]
        
            if val == 0x01:
                self.onButtonDown(but)
            if val == 0x00:
                self.onButtonUp(but)
            if val == 0xB1:
                self.onButtonHold(but)
            

    def onButtonUp(self, but):
        self.rnd.render ( "Key pressed: ", self._button_desc[but] + " UP",'')

    def onButtonDown(self, but):
        self.rnd.render ( "Key pressed: ", self._button_desc[but] + " DOWN",'')
        
    def onButtonHold(self, but):
        self.rnd.render ( "Key pressed: ", self._button_desc[but] + " HOLD",'')

class render:
    lock = threading.Lock()
    
    def __init__(self, isRaw):
         self.current_pos = 0
         self.last_pos = -1
         self.isRaw = isRaw  
         self.dict = {}
         
    def moveCursor(self, line):
        if self.current_pos < line:
            cycle = line - self.current_pos
            strs='\033['+ str(cycle) + 'E'  # move cursor down
            print(strs, end='', flush=True)
        
        if self.current_pos > line:
            cycle = self.current_pos - line
            strs='\033['+ str(cycle) + 'F'  # move cursor up
            print(strs, end='', flush=True)
        
        self.current_pos = line
                    
    def getLine(self, label):
        saved_pos = self.current_pos
        if label not in self.dict:
            self.last_pos = self.last_pos + 1       # assign a new line
            self.dict[label] = self.last_pos
            if self.last_pos > 0 :                       # go to end of the screen
                self.moveCursor (self.last_pos)
            print()                                 # print a new line to scroll the screenand return to previous line
            print('\033[F', end='', flush=True)
            if self.last_pos > 0 :                  # go back to original position
                self.moveCursor (saved_pos)
            print()             
        
        return self.dict[label]
        
    def printDashboard(self, label, data, unit):
        self.lock.acquire()
        self.moveCursor(self.getLine(label))
        print('\033[K', end='', flush=True)  # empty the line
        print(label, data, unit, end='\r', flush=True)
        self.lock.release() 
      
    def render(self, label, data, unit):
        if self.isRaw:
            print(label, data)
        else:
            self.printDashboard(label,data,unit)
    
def enable_tag (tag_name, tagI):
    if tagI == None:
        print ("Warning : no ", tag_name, " on this device")
    else:
        tagI.enable()
    
def main():
    import time
    import sys
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument('host', action='store',help='MAC of BT device')
    parser.add_argument('-n', action='store', dest='count', default=0,
            type=int, help="number of times to loop data")
    parser.add_argument('-t',action='store',type=float, default=5.0, help='time between polling')
    parser.add_argument('-r','--rawdata', action='store_true', default=False,  help='disable dashboard view and print raw data')
    parser.add_argument('-d','--debug', action='store_true', default=False,  help='debug mode')
    parser.add_argument('-T','--temperature', action="store_true",default=False)
    parser.add_argument('-A','--accelerometer', action='store_true',
            default=False)
    parser.add_argument('-H','--humidity', action='store_true', default=False)
    parser.add_argument('-M','--magnetometer', action='store_true',
            default=False)
    parser.add_argument('-B','--barometer', action='store_true', default=False)
    parser.add_argument('-G','--gyroscope', action='store_true', default=False)
    parser.add_argument('-K','--keypress', action='store_true', default=False)
    parser.add_argument('-L','--light', action='store_true', default=False)
    parser.add_argument('-P','--battery', action='store_true', default=False)

    parser.add_argument('--all', action='store_true', default=False)
    
    arg = parser.parse_args(sys.argv[1:])
    
    # render class
    rnd = render(arg.rawdata)
        
    # traceback and exceptions when --debug only
    def exception_handler(exception_type, exception, traceback):
        rnd.render(exception,'','')
        print()
    
    if not arg.debug:
        sys.tracebacklimit=0
        sys.excepthook = exception_handler

    print('Connecting to ' + arg.host)

    tag = SensorTag(arg.host)
         
    print('Connected to ',tag.version,' sensortag device')
        
    # Setting delegate to handle notifications
    if tag.version == SENSORTAG_1352R:
        tag.setDelegate(SensorDelegate(rnd))
    else:
        tag.setDelegate(KeypressDelegate())   
        
    # Enabling selected sensors
    if arg.temperature or arg.all:
        enable_tag('temperature',tag.IRtemperature)
    if arg.humidity or arg.all:
        enable_tag('humidity',tag.humidity)
    if arg.barometer or arg.all:
        enable_tag('barometer', tag.barometer)
    if arg.accelerometer or arg.all:
        enable_tag('accelerometer', tag.accelerometer)
    if arg.magnetometer or arg.all:
        enable_tag('magnetometer', tag.magnetometer)
    if arg.gyroscope or arg.all:
        enable_tag('giroscope', tag.gyroscope)
    if arg.battery or arg.all:
        enable_tag('battery', tag.battery)
    if arg.keypress or arg.all:
        enable_tag('key press', tag.keypress)
    if arg.light or arg.all:
        enable_tag('Lightmeter',tag.lightmeter)


    # Some sensors (e.g., temperature, accelerometer) need some time for initialization.
    # Not waiting here after enabling a sensor, the first read value might be empty or incorrect.
    time.sleep(1.0)

    counter=1
    
    while True:
       if (arg.temperature or arg.all) and tag.IRtemperature is not None:
           rnd.render('Temp: ', tag.IRtemperature.read(), '°C')
       if (arg.humidity or arg.all) and tag.humidity is not None:
           rnd.render("Humidity: ", tag.humidity.read(),'%')
       if (arg.barometer or arg.all) and tag.barometer is not None:
           rnd.render("Barometer: ", tag.barometer.read(),'')
       if (arg.accelerometer or arg.all) and tag.accelerometer is not None and tag.version != SENSORTAG_1352R:
           rnd.render("Accelerometer: ", tag.accelerometer.read(),'')
       if (arg.magnetometer or arg.all) and tag.magnetometer is not None:
           rnd.render("Magnetometer: ", tag.magnetometer.read(),'')
       if (arg.gyroscope or arg.all) and tag.gyroscope is not None:
           rnd.render("Gyroscope: ", tag.gyroscope.read(),'')
       if (arg.light or arg.all) and tag.lightmeter is not None:
           rnd.render("Light: ", tag.lightmeter.read(),'lux')
       if (arg.battery or arg.all) and tag.battery is not None:
           rnd.render("Battery: ", tag.battery.read(),'%')
       if counter >= arg.count and arg.count != 0:
           break
       
       counter += 1
       tag.waitForNotifications(arg.t)
    
    if tag.version == SENSORTAG_1352R and tag.accelerometer:
        tag.accelerometer.disable()
            
    tag.disconnect()
    del tag
    
    rnd.render('done','','')
    print()

if __name__ == "__main__":
    main()
