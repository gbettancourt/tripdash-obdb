#!/usr/bin/env python3
"""Convierte OBDb (https://github.com/OBDb, CC BY-SA 4.0) al formato compacto de TripDash.

Uso:  python3 tools/obdb/convert.py <carpeta con los repositorios clonados>
Genera App/Resources/OBDb/index.json y un archivo por modelo.

Se omiten: comandos de línea K (proto/init), con direccionamiento extendido o prioridad especial,
los que requieren abrir una sesión de diagnóstico (din/dout) y datos de carrocería
(puertas, cinturones, luces, interruptores) y de celdas individuales de baterías de alto voltaje.
"""
import json, os, re, sys

# Modelos vendidos en Chile que tienen contenido en OBDb.
MODELS = [
    "Toyota-Hilux", "Toyota-Yaris", "Toyota-Corolla", "Toyota-Corolla-Cross", "Toyota-RAV4", "Toyota-Fortuner",
    "Toyota-Land-Cruiser", "Toyota-4Runner", "Ford-Ranger", "Ford-Edge", "Ford-Escape", "Ford-Explorer",
    "Ford-Territory", "Mazda-CX-5", "Mazda-CX-30", "Mazda-3", "Kia-Sportage", "Kia-Rio", "Kia-Seltos", "Kia-Sonet",
    "Kia-Picanto", "Hyundai-Accent", "Hyundai-Tucson", "Hyundai-Santa-Fe", "Peugeot-208", "Peugeot-2008",
    "Peugeot-3008", "Mitsubishi-Outlander", "MG-ZS", "Haval-Jolion", "Suzuki-Swift", "Suzuki-Jimny", "Suzuki-Vitara",
    "Suzuki-Baleno", "Nissan-Kicks", "Nissan-Versa", "Nissan-Frontier", "Renault-Duster", "Subaru-Forester",
    "Jeep-Renegade", "Honda-CR-V", "Volkswagen-Amarok", "Volkswagen-T-Cross", "Chevrolet-Colorado",
    "Chevrolet-Silverado",
]

SKIP_PATHS = ("Doors", "Seatbelts", "Lights", "Cruise control", "DTCs", "Details", "Clocks", "ECU", "Stats",
              "Control", "Battery.Cells", "Battery.Modules", "Battery.EVCC")

# unidad OBDb -> (unidad TripDash, factor, conversión especial)
UNITS = {
    "scalar": ("", 1), "unknown": ("", 1), "hex": ("", 1), "": ("", 1),
    "volts": ("V", 1), "millivolts": ("mV", 1), "celsius": ("°C", 1), "percent": ("%", 1), "degrees": ("°", 1),
    "kilometersPerHour": ("km/h", 1), "rpm": ("rpm", 1), "milliseconds": ("ms", 1), "kilometers": ("km", 1),
    "kilopascal": ("kPa", 1), "newtonMeters": ("Nm", 1), "psi": ("kPa", 6.894757), "bars": ("kPa", 100),
    "amps": ("A", 1), "milliamps": ("mA", 1), "seconds": ("s", 1), "liters": ("L", 1),
    "metersPerSecondSquared": ("m/s²", 1), "ampereHours": ("Ah", 1), "minutes": ("min", 1),
    "gramsPerSecond": ("g/s", 1), "ohms": ("Ω", 1), "gravity": ("g", 1), "kilowatts": ("kW", 1),
    "millimeters": ("mm", 1), "hours": ("h", 1), "megaohms": ("MΩ", 1), "milliohms": ("mΩ", 1),
    "kilowattHours": ("kWh", 1), "miles": ("km", 1.609344), "watts": ("W", 1), "hertz": ("Hz", 1),
    "milesPerHour": ("km/h", 1.609344),
}
BOOL_MAPS = {"offon": {"0": "Apagado", "1": "Encendido"}, "onoff": {"0": "Encendido", "1": "Apagado"},
             "noyes": {"0": "No", "1": "Sí"}, "yesno": {"0": "Sí", "1": "No"}}

# Traducción de los nombres más comunes (frase completa o fragmento).
PHRASES = [
    (r"^Odometer$", "Odómetro"), (r"^Battery voltage$", "Voltaje batería"),
    (r"Transmission fluid temperature", "Temp. fluido transmisión"),
    (r"Transmission temperature", "Temp. transmisión"), (r"Engine oil temperature", "Temp. aceite motor"),
    (r"Engine oil pressure", "Presión aceite motor"), (r"Engine coolant temperature", "Temp. refrigerante"),
    (r"Coolant temperature", "Temp. refrigerante"), (r"Intake air temperature", "Temp. aire admisión"),
    (r"Ambient air temperature", "Temp. ambiente"), (r"Fuel level", "Nivel combustible"),
    (r"Fuel pressure", "Presión combustible"), (r"Fuel temperature", "Temp. combustible"),
    (r"Injection volume", "Volumen inyección"), (r"Accelerator pedal", "Pedal acelerador"),
    (r"Steering wheel angle", "Ángulo del volante"), (r"Steering angle", "Ángulo del volante"),
    (r"Tire pressure", "Presión neumático"), (r"tire pressure", "presión neumático"),
    (r"Tire temperature", "Temp. neumático"), (r"tire temperature", "temp. neumático"),
    (r"Wheel speed", "Velocidad rueda"), (r"wheel speed", "velocidad rueda"),
    (r"Vehicle speed", "Velocidad"), (r"Engine speed", "RPM motor"), (r"Current gear", "Marcha actual"),
    (r"Shift gear", "Marcha seleccionada"), (r"Knock correction", "Corrección detonación"),
    (r"Knock feedback value", "Detonación (retroalimentación)"), (r"Cooling fan duty ratio", "Ventilador (ciclo)"),
    (r"Torque converter", "Convertidor de torque"), (r"Lock-?up", "Lockup"),
    (r"Front left", "Del. izq."), (r"Front right", "Del. der."), (r"Rear left", "Tras. izq."), (r"Rear right", "Tras. der."),
    (r"front left", "del. izq."), (r"front right", "del. der."), (r"rear left", "tras. izq."), (r"rear right", "tras. der."),
    (r"Spare", "Repuesto"), (r", variant (\d+)", r" (var. \1)"), (r" var\.(\d+)", r" (var. \1)"),
    (r"cylinder (\d)", r"cilindro \1"), (r"cyl\.(\d)", r"cil. \1"), (r", bank (\d)", r", banco \1"), (r"bank (\d)", r"banco \1"),
    (r"Rough idle", "Ralentí irregular"), (r"Misfire", "Falla de encendido"), (r"Distance", "Distancia"),
    (r"Battery current", "Corriente batería"), (r"Battery temperature", "Temp. batería"),
    (r"State of charge", "Carga batería"), (r"Brake", "Freno"), (r"Yaw rate", "Velocidad de giro"),
    (r"Lateral acceleration", "Aceleración lateral"), (r"Longitudinal acceleration", "Aceleración longitudinal"),
]


def translate(name):
    out = name
    for pat, rep in PHRASES:
        out = re.sub(pat, rep, out)
    return out


def num(v):
    return int(v) if isinstance(v, float) and v.is_integer() else v


def convert(repo_dir, model):
    data = json.load(open(os.path.join(repo_dir, model, "signalsets/v3/default.json")))
    cmds = []
    for c in data.get("commands", []):
        if any(k in c for k in ("proto", "init", "eax", "pri", "din", "dout")):
            continue
        mode, pid = next(iter(c["cmd"].items()))
        if mode not in ("21", "22"):
            continue
        sigs = []
        for s in c["signals"]:
            path = s.get("path", "")
            if path.startswith(SKIP_PATHS):
                continue
            f = s["fmt"]
            unit, factor = UNITS.get(f.get("unit", ""), (f.get("unit", ""), 1))
            sig = {"i": s["id"], "n": translate(s["name"]), "u": unit, "l": f["len"]}
            if path:
                sig["p"] = path
            for k_in, k_out in (("bix", "b"), ("mul", "mul"), ("div", "div"), ("add", "add"), ("min", "min"),
                                ("max", "max"), ("nullmin", "nmin"), ("nullmax", "nmax")):
                if k_in in f:
                    sig[k_out] = num(f[k_in])
            if f.get("sign"):
                sig["sg"] = 1
            if f.get("blsb"):
                sig["le"] = 1
            if factor != 1:
                sig["f"] = factor
            if f.get("unit") == "fahrenheit":
                sig["u"] = "°C"
                sig["f2c"] = 1
            if "map" in f:
                sig["map"] = {str(k): (v if isinstance(v, str) else str(v)) for k, v in f["map"].items()}
            elif f.get("unit") in BOOL_MAPS:
                sig["map"] = BOOL_MAPS[f["unit"]]
                sig["u"] = ""
            sigs.append(sig)
        if not sigs:
            continue
        cmd = {"h": c["hdr"], "c": mode + pid, "s": sigs}
        if "rax" in c:
            cmd["r"] = c["rax"]
        if c.get("fcm1"):
            cmd["fc"] = 1
        flt = c.get("filter") or {}
        if "from" in flt:
            cmd["y0"] = flt["from"]
        if "to" in flt:
            cmd["y1"] = flt["to"]
        if "years" in flt:
            cmd["ys"] = flt["years"]
        cmds.append(cmd)
    make, _, name = model.partition("-")
    return {"model": model, "make": make, "name": name.replace("-", " "), "commands": cmds}


def main():
    src = sys.argv[1]
    out = os.path.join(os.path.dirname(__file__), "../../App/Resources/OBDb")
    os.makedirs(out, exist_ok=True)
    index = []
    for m in MODELS:
        if not os.path.exists(os.path.join(src, m, "signalsets/v3/default.json")):
            print("falta", m)
            continue
        d = convert(src, m)
        n = sum(len(c["s"]) for c in d["commands"])
        if n == 0:
            continue
        with open(os.path.join(out, f"OBDb-{m}.json"), "w") as fh:
            json.dump(d, fh, ensure_ascii=False, separators=(",", ":"))
        index.append({"model": m, "make": d["make"], "name": d["name"], "signals": n})
        print(f"{m}: {len(d['commands'])} comandos, {n} datos")
    with open(os.path.join(out, "OBDb-index.json"), "w") as fh:
        json.dump(index, fh, ensure_ascii=False, separators=(",", ":"))


if __name__ == "__main__":
    main()
