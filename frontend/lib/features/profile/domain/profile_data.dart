class ProfileData {
  final String name;
  final String email;

  const ProfileData({required this.name, required this.email});

  String get initials {
    final cleaned = name.trim();

    if (cleaned.isEmpty) {
      return 'U';
    }

    final parts = cleaned
        .split(RegExp(r'\s+'))
        .where((part) => part.isNotEmpty)
        .toList();

    if (parts.length == 1) {
      return parts.first.substring(0, 1).toUpperCase();
    }

    return (parts.first.substring(0, 1) + parts.last.substring(0, 1))
        .toUpperCase();
  }
}
