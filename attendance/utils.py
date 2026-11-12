import math


def calculate_haversine_distance(lat1, lon1, lat2, lon2):
    """
    حساب المسافة بين نقطتين جغرافيتين (GPS) بالأمتار باستخدام معادلة Haversine.
    lat1, lon1: إحداثيات موقع الموظف
    lat2, lon2: إحداثيات موقع العمل المعتمد (Worksite)
    النتيجة: المسافة بالأمتار (float)
    """
    # تحويل الإحداثيات إلى راديان
    lat1_rad = math.radians(float(lat1))
    lon1_rad = math.radians(float(lon1))
    lat2_rad = math.radians(float(lat2))
    lon2_rad = math.radians(float(lon2))

    # نصف قطر الأرض بالكيلومترات
    radius_earth_km = 6371.0

    # الفروقات
    dlat = lat2_rad - lat1_rad
    dlon = lon2_rad - lon1_rad

    # صيغة الهافرسين
    a = (math.sin(dlat / 2) ** 2 +
         math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(dlon / 2) ** 2)
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

    distance_meters = radius_earth_km * c * 1000.0
    return round(distance_meters, 2)
